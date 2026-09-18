from __future__ import annotations

from dataclasses import dataclass

from backend.gpt_director import GPTDirectorTask


SAFE_IMAGE_MIMES = {'image/jpeg', 'image/png', 'image/webp'}
MIME_EXTENSIONS = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}


@dataclass(frozen=True)
class AuthorizedSourcePage:
    task_id: str
    token: str
    page: int
    resource_name: str


def authorize_source_page(task: GPTDirectorTask, page: int) -> AuthorizedSourcePage:
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        raise ValueError('invalid_source_page')
    if page not in task.source.selectedPages:
        raise PermissionError('source_page_not_selected')
    if not any(item.page == page for item in task.source.pages):
        raise PermissionError('source_page_not_authorized')
    return AuthorizedSourcePage(
        task_id=task.id,
        token=task.source.token,
        page=page,
        resource_name=f'page-{page:03d}',
    )


def safe_image_mime(value: str | None) -> str:
    mime = (value or '').split(';', 1)[0].strip().lower()
    if mime not in SAFE_IMAGE_MIMES:
        raise ValueError('unsupported_source_image_mime')
    return mime


def neutral_image_name(page: int, mime: str) -> str:
    safe_mime = safe_image_mime(mime)
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        raise ValueError('invalid_source_page')
    return f'page-{page:03d}.{MIME_EXTENSIONS[safe_mime]}'


def safe_probe_metadata(page: int, mime: str, byte_count: int, encoded_size: int) -> dict:
    safe_mime = safe_image_mime(mime)
    if byte_count < 1 or encoded_size < 1:
        raise ValueError('empty_source_image')
    return {
        'page': page,
        'mime': safe_mime,
        'bytes': byte_count,
        'base64EncodedSize': encoded_size,
        'resourceName': neutral_image_name(page, safe_mime),
        'transferMode': 'IMAGE_CONTENT',
    }
