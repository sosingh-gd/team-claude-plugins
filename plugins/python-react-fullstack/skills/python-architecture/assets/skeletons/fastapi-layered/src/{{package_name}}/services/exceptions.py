from {{package_name}}.core.exceptions import NotFoundError


class ItemNotFoundError(NotFoundError):
    def __init__(self, item_id: int) -> None:
        super().__init__(f"Item {item_id} not found")
