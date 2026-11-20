from pathlib import Path


BADGE_FONT_FAMILY = 'Times New Roman'
FONT_DIRECTORY = Path('/usr/local/share/fonts/badge')
BADGE_FONTS = {
    False: ('BadgeTimesRegular', FONT_DIRECTORY / 'Times.TTF'),
    True: ('BadgeTimesBold', FONT_DIRECTORY / 'Timesbd.TTF'),
}
