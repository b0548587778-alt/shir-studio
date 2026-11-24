כדי להוסיף סגנון ליווי: מעתיקים אחד מקבצי ה-json כאן, משנים שם (name), תיאור ותבנית.
t = מיקום בתוך התיבה (0 עד 4 פעמות), d = אורך בפעמות, n = איזה צליל מהאקורד,
v = עוצמה (0 עד 1). "free" = מה מנגנים כשהשיר מושר בקצב חופשי.
כלים: piano, guitar, steel_guitar, bass, acoustic_bass, strings, slow_strings, brass, trumpet, violin, clarinet, flute, organ, accordion, choir, choir_oo, bass_voice, timpani, drums
תופים: kick, snare, hat, open_hat, tambourine, crash, clap
צלילים: root, root_low, third, fifth, fifth_low, octave, third_hi, fifth_hi, chord

אפשרויות נוספות לסגנון: "lead" = הכלי שמנגן את הסולו בסוף (ברירת מחדל: כינור/קלרינט/חליל...),
"solo": false = בלי סולו בסוף. כלי עם "enter" של 8 ומעלה מנגן רק בפזמונים.
תופים נוספים (בערכה החדשה): ride, tom_hi, tom_low
"intro": false = בלי מבוא מנגינה, "counter": false = בלי מנגינות נגד בין המשפטים,
"rich_chords": true = אקורדים עשירים (ספטאקורדים), "voices": {"harmony": "three", "choir": true} = מקהלה מהקול של הזמר.
כלי נוסף: cello. באקורדים שכותבים ידנית אפשר גם E7, Am7, Fmaj7.
כלים חדשים: harp, oboe, bassoon, horn, marimba, glockenspiel, bells. "ritardando": false = בלי האטה בסיום.
"meter": 3 או 6 = הסגנון מנוגן במשקל 3/4 (ואלס) או 6/8. בסגנון 6/8 כותבים את התבנית כרגיל ב-4 פעמות, והתוכנה ממירה:
פעמות 0 ו-2 הן שתי הפעמות הראשיות, 1 ו-1.5 (וכן 3 ו-3.5) הן שתי השמיניות שאחריהן.
"intro_kind": "start" / "chorus" / "long" / "short" = מה מנוגן בפתיח (תחילת השיר, סוף הפזמון, כל המשפט הראשון, או בלי מנגינה).
"ending": "full" / "hits" / "fade" / "short" = הסיום (סולו והאטה ואקורד ארוך, שלוש מכות חדות, דעיכה, או אקורד מיד אחרי השירה).
"flourish": false = בלי ה'טיפוס' של הפסנתר או הנבל על אקורד הסיום.
