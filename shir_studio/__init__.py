from .i18n import tx          # חייב להיות ראשון: השפה נטענת לפני כל שאר התוכנה

APP_NAME = tx("שיר סטודיו")
try:                                    # הקובץ נוצר בזמן בניית קובץ ההתקנה, עם מספר הגרסה האמיתי
    from ._version import VERSION as APP_VERSION
except ImportError:
    APP_VERSION = "1.0.0"
