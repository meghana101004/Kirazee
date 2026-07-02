from django.db import connection

def resolve_subcategory_name(sub_category_id):
    """
    Utility to resolve the sub_category name (category_name) 
    from a sub_category_id (category_id) in universal_Categories.
    Returns the name as a string or None if not found.
    """
    if not sub_category_id:
        return None
        
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT category_name FROM universal_Categories WHERE category_id = %s", 
                [sub_category_id]
            )
            row = cursor.fetchone()
            if row:
                return row[0]
    except Exception:
        pass
    return None
