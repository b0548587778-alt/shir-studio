APP_NAME = "שיר סטודיו"
try:                                    # הקובץ נוצר בזמן בניית קובץ ההתקנה, עם מספר הגרסה האמיתי
    from ._version import VERSION as APP_VERSION
except ImportError:
    APP_VERSION = "1.0.0"
