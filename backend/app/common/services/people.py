


def name_sort_key(full_name: str, user_id: int = 0) -> tuple[str, int]:
    normalized = " ".join(full_name.split()).casefold().replace("ё", "е")
    return normalized, user_id
