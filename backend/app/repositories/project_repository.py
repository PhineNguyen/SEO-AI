"""Repository for Project, ProjectSettings, Website, and Competitor persistence."""

import uuid

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.models.project import Competitor, Project, ProjectSettings, Website


class ProjectRepository:
    """Data access layer for project management entities."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_project(
        self,
        *,
        owner_id: uuid.UUID,
        name: str,
        niche: str | None,
        target_country: str,
        target_language: str,
        target_audience: str | None,
    ) -> Project:
        """Create and flush a new Project row."""
        project = Project(
            owner_id=owner_id,
            name=name,
            niche=niche,
            target_country=target_country,
            target_language=target_language,
            target_audience=target_audience,
        )
        self.db.add(project)
        self.db.flush()
        return project

    def get_by_id(
        self,
        project_id: uuid.UUID,
        *,
        with_relations: bool = False,
    ) -> Project | None:
        """Fetch a project by UUID, optionally eager-loading settings, websites, competitors."""
        stmt = select(Project).where(Project.id == project_id)
        if with_relations:
            stmt = stmt.options(
                selectinload(Project.settings),
                selectinload(Project.websites),
                selectinload(Project.competitors),
            )
        return self.db.scalar(stmt)

    def list_projects(
        self,
        *,
        owner_id: uuid.UUID | None,
        status: str | None,
        search: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Project], int]:
        """List projects matching optional owner, status, and search filters."""
        filters = []
        if owner_id is not None:
            filters.append(Project.owner_id == owner_id)
        if status is not None:
            filters.append(Project.status == status)
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    Project.name.ilike(pattern),
                    Project.niche.ilike(pattern),
                )
            )

        count_stmt = select(func.count()).select_from(Project).where(*filters)
        total = int(self.db.scalar(count_stmt) or 0)

        items_stmt = (
            select(Project)
            .where(*filters)
            .order_by(Project.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items = list(self.db.scalars(items_stmt).all())
        return items, total

    def delete_project(self, project: Project) -> None:
        """Mark a project for deletion."""
        self.db.delete(project)

    def create_default_settings(self, project_id: uuid.UUID) -> ProjectSettings:
        """Create and flush default ProjectSettings for a project."""
        settings = ProjectSettings(project_id=project_id)
        self.db.add(settings)
        self.db.flush()
        return settings

    def get_settings(self, project_id: uuid.UUID) -> ProjectSettings | None:
        """Fetch settings for a project."""
        return self.db.scalar(
            select(ProjectSettings).where(ProjectSettings.project_id == project_id)
        )

    def list_websites(self, project_id: uuid.UUID) -> list[Website]:
        """Return websites for a project ordered by primary flag then created_at."""
        stmt = (
            select(Website)
            .where(Website.project_id == project_id)
            .order_by(Website.is_primary.desc(), Website.created_at.asc())
        )
        return list(self.db.scalars(stmt).all())

    def get_website(
        self,
        project_id: uuid.UUID,
        website_id: uuid.UUID,
    ) -> Website | None:
        """Fetch a single website scoped to a project."""
        return self.db.scalar(
            select(Website).where(
                Website.project_id == project_id,
                Website.id == website_id,
            )
        )

    def unset_primary_website(
        self,
        project_id: uuid.UUID,
        *,
        exclude_website_id: uuid.UUID | None = None,
    ) -> None:
        """Demote existing primary website(s) within a project before promoting another."""
        stmt = (
            update(Website)
            .where(Website.project_id == project_id, Website.is_primary.is_(True))
            .values(is_primary=False)
            .execution_options(synchronize_session="fetch")
        )
        if exclude_website_id is not None:
            stmt = stmt.where(Website.id != exclude_website_id)
        self.db.execute(stmt)
        self.db.flush()

    def create_website(
        self,
        *,
        project_id: uuid.UUID,
        domain: str,
        base_url: str,
        gsc_property_uri: str | None,
        is_primary: bool,
    ) -> Website:
        """Add and flush a new Website record."""
        website = Website(
            project_id=project_id,
            domain=domain,
            base_url=base_url,
            gsc_property_uri=gsc_property_uri,
            is_primary=is_primary,
        )
        self.db.add(website)
        self.db.flush()
        return website

    def delete_website(self, website: Website) -> None:
        """Mark a website for deletion."""
        self.db.delete(website)

    def list_competitors(self, project_id: uuid.UUID) -> list[Competitor]:
        """Return competitors for a project ordered by created_at."""
        stmt = (
            select(Competitor)
            .where(Competitor.project_id == project_id)
            .order_by(Competitor.created_at.asc())
        )
        return list(self.db.scalars(stmt).all())

    def get_competitor(
        self,
        project_id: uuid.UUID,
        competitor_id: uuid.UUID,
    ) -> Competitor | None:
        """Fetch a single competitor scoped to a project."""
        return self.db.scalar(
            select(Competitor).where(
                Competitor.project_id == project_id,
                Competitor.id == competitor_id,
            )
        )

    def create_competitor(
        self,
        *,
        project_id: uuid.UUID,
        domain: str,
        name: str | None,
        notes: str | None,
    ) -> Competitor:
        """Add and flush a new Competitor record."""
        competitor = Competitor(
            project_id=project_id,
            domain=domain,
            name=name,
            notes=notes,
        )
        self.db.add(competitor)
        self.db.flush()
        return competitor

    def delete_competitor(self, competitor: Competitor) -> None:
        """Mark a competitor for deletion."""
        self.db.delete(competitor)
