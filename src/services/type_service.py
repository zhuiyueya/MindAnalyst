from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.models import Author, ContentItem
from src.repositories.content_repo import ContentRepository


class TypeService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.contents = ContentRepository(session)

    async def set_author_type(self, author_id: str, author_type_raw: str | None) -> dict[str, str | None]:
        author = await self.session.get(Author, author_id)
        if not author:
            raise HTTPException(status_code=404, detail="Author not found")

        author_type = author_type_raw.strip() if author_type_raw else None
        author.author_type = author_type or None
        author.author_type_source = "user" if author_type else None
        self.session.add(author)

        contents = await self.contents.list_by_author(author_id)
        for content in contents:
            if author_type:
                content.content_type = author_type
                content.content_type_source = "author_inherit"
            elif content.content_type_source == "author_inherit":
                content.content_type = None
                content.content_type_source = None
            self.session.add(content)

        await self.session.commit()
        return {"author_id": author_id, "author_type": author.author_type}

    async def set_video_type(self, video_id: str, content_type_raw: str | None) -> dict[str, object]:
        video = await self.contents.get_by_id_or_external_id(video_id)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        if video.author_id:
            author = await self.session.get(Author, video.author_id)
            if author and author.author_type:
                raise HTTPException(
                    status_code=400,
                    detail="Author type set; clear author type before overriding video type",
                )

        content_type = content_type_raw.strip() if content_type_raw else None
        video.content_type = content_type or None
        video.content_type_source = "user" if content_type else None
        self.session.add(video)
        await self.session.commit()
        await self.session.refresh(video)
        return {"video": video.model_dump()}
