# רכיבים ורישיונות - שיר סטודיו

כל הרכיבים ברשימה מתירים שימוש ומכירה מסחרית.
הערה: רכיבים ברישיון LGPL מותרים במכירה בתנאי שהם נשארים קבצים נפרדים (כך זה בנוי),
שמצרפים את הרשימה הזו ואת נוסח הרישיון, ושמאפשרים לקבל את קוד המקור של אותם רכיבים.
לפני מכירה מומלץ להראות את הרשימה לעורך דין.

| רכיב | תפקיד | רישיון | מכירה מסחרית |
|---|---|---|---|
| קוד התוכנה עצמו | נכתב במיוחד: ניקוי רעשים, זיהוי גובה צליל (YIN), תיקון זיופים (PSOLA), זיהוי סולם, קצב ואקורדים, עיבוד וערבוב | שלך | כן |
| צלילי כלי הנגינה והמקהלה | הקלטות אמיתיות מתוך FluidR3_GM מאת Frank Wen (קובץ shir_studio/samples/pack.npz) | MIT | כן - חובה לצרף את הודעת הרישיון (מצורפת למטה) |
| פסנתר, גיטרה קלאסית וקלרינט | UprightPianoKW, SpanishClassicalGuitar, Clarinet מאתר FreePats (freepats.zenvoid.org) | CC0 (נחלת הכלל) | כן |
| כינור, מיתרים, צ'לו, חצוצרה, טרומבון, חליל, קונטרבס, נבל, אבוב, בסון, קרן יער, מרימבה, פעמוני זכוכית ופעמונים | VS Chamber Orchestra: Community Edition (VSCO-2-CE) מאת Versilian Studios | CC0 (נחלת הכלל) | כן |
| ערכת התופים | MuldjordKit מאת Lars Muldjord (גרסת FreePats) | CC-BY 4.0 | כן - חובה לציין קרדיט (מצורף למטה) |
| קול הבס "דום" בסגנון הווקאלי | נוצר בקוד עצמו (סינתזה) | שלך | כן |
| סמל התוכנה | צויר בקוד | שלך | כן |
| Python | שפת התכנות | PSF | כן |
| Qt / PySide6 | המסך והכפתורים | LGPL-3.0 | כן (בתנאי LGPL) |
| NumPy | חישובים | BSD-3 | כן |
| SciPy | עיבוד קול | BSD-3 | כן |
| soundfile + libsndfile | קריאת קבצי קול | BSD-3 / LGPL-2.1 | כן (בתנאי LGPL) |
| sounddevice + PortAudio | מיקרופון ורמקולים | MIT | כן |
| lameenc + LAME | יצירת MP3 | LGPL | כן (בתנאי LGPL). הפטנטים על MP3 פגו ב-2017 |
| cffi | חיבור לרכיבים | MIT | כן |
| PyInstaller | אריזת התוכנה | GPL עם חריגה שמתירה הפצה מסחרית | כן |
| Inno Setup | קובץ ההתקנה | רישיון Inno Setup (חינמי, מתיר מסחרי) | כן |

השיטות (YIN, PSOLA, Karplus-Strong, פרופילי קרומהנסל) הן שיטות מדעיות מפורסמות, ללא פטנטים בתוקף ידועים.

---
## הודעת הרישיון של FluidR3_GM (חובה לצרף)
Copyright (c) 2000-2002, 2008 Frank Wen

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

---
## קרדיט לערכת התופים (CC-BY 4.0 - חובה לצרף)
Drum samples: "MuldjordKit" by Lars Muldjord (www.muldjord.com, www.drumgizmo.org),
SF2 version by the FreePats project. Licensed under Creative Commons Attribution 4.0 International
(https://creativecommons.org/licenses/by/4.0/). The samples were trimmed and converted to mono.
