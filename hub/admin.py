from django.contrib import admin
from .models import (Classroom, UserAnswer, Unscramble, LabelImages, EmbeddedTask, Lesson,
                     WordList, MatchUpTheWords, Test, TrueOrFalse, MakeASentence, SortIntoColumns, Audio,
                     FillInTheBlanks, UserAutogenerationPreferences, SavedUnsplashImage, Pdf)

admin.site.register(Classroom)
admin.site.register(UserAnswer)
admin.site.register(Unscramble)
admin.site.register(LabelImages)
admin.site.register(EmbeddedTask)
admin.site.register(Lesson)
admin.site.register(WordList)
admin.site.register(MatchUpTheWords)
admin.site.register(Test)
admin.site.register(TrueOrFalse)
admin.site.register(MakeASentence)
admin.site.register(SortIntoColumns)
admin.site.register(Audio)
admin.site.register(FillInTheBlanks)
admin.site.register(UserAutogenerationPreferences)
admin.site.register(SavedUnsplashImage)
admin.site.register(Pdf)