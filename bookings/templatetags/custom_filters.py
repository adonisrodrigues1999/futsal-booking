from django import template
from datetime import date

register = template.Library()


@register.filter
def format_date_with_day(date_obj):
    """
    Format a date object to include the day of the week (3 letters) and date.
    Example: "Mon, Jul 15, 2026" or "Mon 15 Jul 2026"
    """
    if not date_obj:
        return ""
    
    if isinstance(date_obj, str):
        try:
            date_obj = date.fromisoformat(date_obj)
        except (ValueError, AttributeError):
            return date_obj
    
    # Get the day of the week in 3 letters (Mon, Tue, Wed, etc.)
    day_of_week = date_obj.strftime('%a')
    # Format: "Mon, Jul 15, 2026"
    return date_obj.strftime(f'{day_of_week}, %b %d, %Y')


@register.filter
def day_of_week_short(date_obj):
    """
    Get the short day of the week (3 letters) for a date object.
    Example: "Mon", "Tue", "Wed"
    """
    if not date_obj:
        return ""
    
    if isinstance(date_obj, str):
        try:
            date_obj = date.fromisoformat(date_obj)
        except (ValueError, AttributeError):
            return date_obj
    
    return date_obj.strftime('%a')


@register.filter
def day_of_week_full(date_obj):
    """
    Get the full day of the week for a date object.
    Example: "Monday", "Tuesday", "Wednesday"
    """
    if not date_obj:
        return ""
    
    if isinstance(date_obj, str):
        try:
            date_obj = date.fromisoformat(date_obj)
        except (ValueError, AttributeError):
            return date_obj
    
    return date_obj.strftime('%A')
