APP_NAME = "שיר סטודיו"
try:                                   # מספר הגרסה נכתב בזמן בניית קובץ ההתקנה
    from ._version import VERSION as APP_VERSION
except Exception:
    APP_VERSION = "1.0.0"
