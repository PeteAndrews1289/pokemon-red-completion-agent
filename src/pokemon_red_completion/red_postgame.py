"""Recognize the native Continue menu without ever selecting New Game."""


def continue_menu_visible(rows: tuple[str, ...]) -> bool:
    return (len(rows) == 18 and rows[2][2:10] == "CONTINUE"
            and rows[4][2:10] == "NEW GAME" and rows[6][2:8] == "OPTION")


def require_continue_selection(rows, cursor):
    if (not continue_menu_visible(rows) or cursor.selected_visible_index != 0
            or cursor.maximum_visible_index != 2 or cursor.top_x != 1 or cursor.top_y != 2):
        raise ValueError("native Continue is not the verified selected menu entry")
