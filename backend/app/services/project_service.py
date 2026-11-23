"""Application service orchestrating Project, Settings, Website, and Competitor operations."""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.project import Competitor, Project, ProjectSettings, Website
from app.models.user import User
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import (
    CompetitorCreate,
    CompetitorUpdate,
    ProjectCreate,
    ProjectSettingsUpdate,
    ProjectUpdate,
    WebsiteCreate,
    WebsiteUpdate,
)


class ProjectNotFoundError(Exception):
    """Raised when a project does not exist or is not accessible to the caller."""


class WebsiteNotFoundError(Exception):
    """Raised when a website does not exist within the target project."""


class CompetitorNotFoundError(Exception):
    """Raised when a competitor does not exist within the target project."""


class DuplicateResourceError(Exception):
    """Raised when creating or updating violates a uniqueness constraint."""


class ProjectService:
    """Business logic and authorization checks for Project Management."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ProjectRepository(db)

    def _get_authorized_project(
        self,
        project_id: uuid.UUID,
        current_user: User,
        *,
        with_relations: bool = False,
    ) -> Project:
        project = self.repo.get_by_id(project_id, with_relations=with_relations)
        if project is None:
            raise ProjectNotFoundError("Project not found")
        if project.owner_id != current_user.id and current_user.role != "admin":
            raise ProjectNotFoundError("Project not found")
        return project

    def create_project(self, current_user: User, payload: ProjectCreate) -> Project:
        """Create a project and initialize its default settings in one transaction."""
        try:
            project = self.repo.create_project(
                owner_id=current_user.id,
                name=payload.name,
                niche=payload.niche,
                target_country=payload.target_country,
                target_language=payload.target_language,
                target_audience=payload.target_audience,
            )
            self.repo.create_default_settings(project.id)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateResourceError(
                f"Project with name '{payload.name}' already exists"
            ) from exc

        loaded = self.repo.get_by_id(project.id, with_relations=True)
        assert loaded is not None
        return loaded

    def list_projects(
        self,
        current_user: User,
        *,
        status: str | None = None,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Project], int]:
        """List projects owned by the current user (or all for admin)."""
        owner_filter = None if current_user.role == "admin" else current_user.id
        return self.repo.list_projects(
            owner_id=owner_filter,
            status=status,
            search=search,
            limit=limit,
            offset=offset,
        )

    def get_project(self, project_id: uuid.UUID, current_user: User) -> Project:
        """Retrieve a project with settings, websites, and competitors."""
        return self._get_authorized_project(project_id, current_user, with_relations=True)

    def update_project(
        self,
        project_id: uuid.UUID,
        current_user: User,
        payload: ProjectUpdate,
    ) -> Project:
        """Apply partial updates to an authorized project."""
        project = self._get_authorized_project(project_id, current_user)
        updates = payload.model_dump(exclude_unset=True)
        for field_name, value in updates.items():
            setattr(project, field_name, value)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateResourceError("A project with that name already exists") from exc

        self.db.refresh(project)
        return project

    def delete_project(self, project_id: uuid.UUID, current_user: User) -> None:
        """Delete an authorized project and cascade its child resources."""
        project = self._get_authorized_project(project_id, current_user)
        self.repo.delete_project(project)
        self.db.commit()

    def get_settings(self, project_id: uuid.UUID, current_user: User) -> ProjectSettings:
        """Retrieve project settings, creating defaults if missing."""
        self._get_authorized_project(project_id, current_user)
        settings = self.repo.get_settings(project_id)
        if settings is None:
            settings = self.repo.create_default_settings(project_id)
            self.db.commit()
            self.db.refresh(settings)
        return settings

    def update_settings(
        self,
        project_id: uuid.UUID,
        current_user: User,
        payload: ProjectSettingsUpdate,
    ) -> ProjectSettings:
        """Update configurable project settings."""
        self._get_authorized_project(project_id, current_user)
        settings = self.repo.get_settings(project_id)
        if settings is None:
            settings = self.repo.create_default_settings(project_id)

        updates = payload.model_dump(exclude_unset=True)
        for field_name, value in updates.items():
            setattr(settings, field_name, value)

        self.db.commit()
        self.db.refresh(settings)
        return settings

    def list_websites(self, project_id: uuid.UUID, current_user: User) -> list[Website]:
        """List websites belonging to an authorized project."""
        self._get_authorized_project(project_id, current_user)
        return self.repo.list_websites(project_id)

    def add_website(
        self,
        project_id: uuid.UUID,
        current_user: User,
        payload: WebsiteCreate,
    ) -> Website:
        """Attach a website to a project, enforcing single primary website per project."""
        self._get_authorized_project(project_id, current_user)
        try:
            if payload.is_primary:
                self.repo.unset_primary_website(project_id)
            website = self.repo.create_website(
                project_id=project_id,
                domain=payload.domain,
                base_url=payload.base_url,
                gsc_property_uri=payload.gsc_property_uri,
                is_primary=payload.is_primary,
            )
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateResourceError(
                f"Website domain '{payload.domain}' already exists in this project"
            ) from exc

        self.db.refresh(website)
        return website

    def update_website(
        self,
        project_id: uuid.UUID,
        website_id: uuid.UUID,
        current_user: User,
        payload: WebsiteUpdate,
    ) -> Website:
        """Update a project website and atomically handle primary promotion."""
        self._get_authorized_project(project_id, current_user)
        website = self.repo.get_website(project_id, website_id)
        if website is None:
            raise WebsiteNotFoundError("Website not found")

        updates = payload.model_dump(exclude_unset=True)
        try:
            if updates.get("is_primary") is True:
                self.repo.unset_primary_website(project_id, exclude_website_id=website_id)
            for field_name, value in updates.items():
                setattr(website, field_name, value)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateResourceError("Website domain already exists in this project") from exc

        self.db.refresh(website)
        return website

    def delete_website(
        self,
        project_id: uuid.UUID,
        website_id: uuid.UUID,
        current_user: User,
    ) -> None:
        """Remove a website from an authorized project."""
        self._get_authorized_project(project_id, current_user)
        website = self.repo.get_website(project_id, website_id)
        if website is None:
            raise WebsiteNotFoundError("Website not found")
        self.repo.delete_website(website)
        self.db.commit()

    def list_competitors(self, project_id: uuid.UUID, current_user: User) -> list[Competitor]:
        """List competitors belonging to an authorized project."""
        self._get_authorized_project(project_id, current_user)
        return self.repo.list_competitors(project_id)

    def add_competitor(
        self,
        project_id: uuid.UUID,
        current_user: User,
        payload: CompetitorCreate,
    ) -> Competitor:
        """Add a competitor domain to a project."""
        self._get_authorized_project(project_id, current_user)
        try:
            competitor = self.repo.create_competitor(
                project_id=project_id,
                domain=payload.domain,
                name=payload.name,
                notes=payload.notes,
            )
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateResourceError(
                f"Competitor domain '{payload.domain}' already exists in this project"
            ) from exc

        self.db.refresh(competitor)
        return competitor

    def update_competitor(
        self,
        project_id: uuid.UUID,
        competitor_id: uuid.UUID,
        current_user: User,
        payload: CompetitorUpdate,
    ) -> Competitor:
        """Update a project competitor."""
        self._get_authorized_project(project_id, current_user)
        competitor = self.repo.get_competitor(project_id, competitor_id)
        if competitor is None:
            raise CompetitorNotFoundError("Competitor not found")

        updates = payload.model_dump(exclude_unset=True)
        for field_name, value in updates.items():
            setattr(competitor, field_name, value)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateResourceError(
                "Competitor domain already exists in this project"
            ) from exc

        self.db.refresh(competitor)
        return competitor

    def delete_competitor(
        self,
        project_id: uuid.UUID,
        competitor_id: uuid.UUID,
        current_user: User,
    ) -> None:
        """Remove a competitor from an authorized project."""
        self._get_authorized_project(project_id, current_user)
        competitor = self.repo.get_competitor(project_id, competitor_id)
        if competitor is None:
            raise CompetitorNotFoundError("Competitor not found")
        self.repo.delete_competitor(competitor)
        self.db.commit()
