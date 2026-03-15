from aiogram import types


TELEGRAM_SAFE_CHUNK_SIZE = 3900


def split_text_chunks(text: str, max_len: int = TELEGRAM_SAFE_CHUNK_SIZE) -> list[str]:
    if not text:
        return [""]
    if len(text) <= max_len:
        return [text]

    chunks = []
    paragraphs = text.split("\n\n")
    current = ""

    for paragraph in paragraphs:
        block = paragraph if not current else f"\n\n{paragraph}"
        candidate = current + block

        if len(candidate) <= max_len:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(paragraph) <= max_len:
            current = paragraph
            continue

        start = 0
        while start < len(paragraph):
            end = min(start + max_len, len(paragraph))
            piece = paragraph[start:end]
            if end < len(paragraph):
                last_space = piece.rfind(" ")
                if last_space > 0:
                    piece = piece[:last_space]
                    end = start + last_space
            chunks.append(piece)
            start = end
            while start < len(paragraph) and paragraph[start] == " ":
                start += 1

    if current:
        chunks.append(current)

    return [chunk for chunk in chunks if chunk]


async def send_long_message(
    message: types.Message,
    text: str,
    reply_markup=None,
    parse_mode: str | None = None,
    max_len: int = TELEGRAM_SAFE_CHUNK_SIZE,
):
    chunks = split_text_chunks(text, max_len=max_len)

    for index, chunk in enumerate(chunks):
        kwargs = {}
        if parse_mode and len(chunks) == 1:
            kwargs["parse_mode"] = parse_mode
        if reply_markup is not None and index == len(chunks) - 1:
            kwargs["reply_markup"] = reply_markup
        await message.answer(chunk, **kwargs)