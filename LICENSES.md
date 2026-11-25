# רכיבים ורישיונות - שיר סטודיו

כל הרכיבים ברשימה מתירים שימוש ומכירה מסחרית.
הערה: רכיבים ברישיון LGPL מותרים במכירה בתנאי שהם נשארים קבצים נפרדים (כך זה בנוי),
שמצרפים את הרשימה הזו ואת נוסח הרישיון, ושמאפשרים לקבל את קוד המקור של אותם רכיבים.
לפני מכירה מומלץ להראות את הרשימה לעורך דין.

| רכיב | תפקיד | רישיון | מכירה מסחרית |
|---|---|---|---|
| קוד התוכנה עצמו | נכתב במיוחד: ניקוי רעשים, זיהוי גובה צליל (YIN), תיקון זיופים (PSOLA), זיהוי סולם, קצב ואקורדים, עיבוד וערבוב | שלך | כן |
| צלילי כלי הנגינה והמקהלה | הקלטות אמיתיות מתוך FluidR3_GM מאת Frank Wen (קובץ shir_studio/samples/pack.npz) | MIT | כן - חובה לצרף את הודעת הרישיון (מצורפת למטה) |
| פסנתר, גיטרה קלאסית, קלרינט ואקורדיון כפתורים | UprightPianoKW, SpanishClassicalGuitar, Clarinet, Button Accordion HN מאתר FreePats (freepats.zenvoid.org) | CC0 (נחלת הכלל) | כן |
| כינור, מיתרים, צ'לו, חצוצרה, טרומבון, חליל, קונטרבס, נבל, אבוב, בסון, קרן יער, מרימבה, פעמוני זכוכית, פעמונים וטימפני | VS Chamber Orchestra: Community Edition (VSCO-2-CE) מאת Versilian Studios | CC0 (נחלת הכלל) | כן |
| ערכת התופים | MuldjordKit מאת Lars Muldjord (גרסת FreePats) | CC-BY 4.0 | כן - חובה לציין קרדיט (מצורף למטה) |
| קול הבס "דום" בסגנון הווקאלי | נוצר בקוד עצמו (סינתזה) | שלך | כן |
| סמל התוכנה | צויר בקוד | שלך | כן |
| בדיקת הרישיון (חתימה דיגיטלית Ed25519, במבנה הרישיונות של SuperSuite) | נכתב במיוחד לפי התקן הפתוח RFC 8032 | שלך (האלגוריתם נחלת הכלל) | כן |
| קובצי השפה (עברית, יידיש, אנגלית) | נכתבו במיוחד | שלך | כן |
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

בשדרוג לשלוש שפות, לסגנון הסימפוני ולרישיון **לא נוסף שום רכיב חיצוני חדש** - הכלים של התזמורת הם אלה שכבר היו ברשימה (VSCO-2-CE, FluidR3_GM, FreePats).

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

---
## מודלי הפרדת הקול והכלים (רישיון MIT - חובה לתת קרדיט)
Vocal separation model: "UVR-MDX-NET Voc FT" from the Ultimate Vocal Remover project
(https://github.com/Anjok07/ultimatevocalremovergui), by Anjok07 and aufr33, based on the MDX-Net
architecture (KUIELab / Woosung Choi) and on vocal models by KimberleyJSN. The UVR project publishes its
models under the MIT License and asks third-party applications to credit UVR and its developers.
File: `shir_studio/models/vocals.onnx` (unmodified;
SHA-256 534b2070fcc7df514b13ef660dc8cbb328679c2374d04354a5c42bb14ecce111).

Drum and bass separation models: "kuielab_a_drums" and "kuielab_a_bass" by KUIELab (Minseok Kim, Woosung Choi
and colleagues, Korea University), from the "KUIELab-MDX-Net" music demixing project
(https://github.com/kuielab/mdx-net-submission, MIT License), as distributed with Ultimate Vocal Remover.
Files: `shir_studio/models/drums.onnx` (SHA-256 40f586b7091934dd6f5563f0cba8f14bad57ce88440da1098bf388ea716c2901)
and `shir_studio/models/bass.onnx` (SHA-256 0c3e77b9963185b1ea6bb46a4b8924137d9370fc1ccdefec7b1b416ef550dcaa), unmodified.

The models run with ONNX Runtime (https://onnxruntime.ai), Copyright (c) Microsoft Corporation, MIT License.
