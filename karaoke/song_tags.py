"""Labels for library songs: duets and kids' songs. Searchable ("duets", "kids") and shown
next to search results. Your files are never renamed; labels live in the library index.

Edit the lists below to add artists, films or songs; labels are recomputed on the next
REFRESH KARAOKE LIBRARY.
"""

from __future__ import annotations

import re

DUET, KIDS, KT = "duet", "kids", "kt"

# Words that search for a label (singular, plural and the like).
SEARCH_WORDS = {
    DUET: {"duet", "duets"},
    KIDS: {"kid", "kids", "children", "childrens", "child", "kidz"},
    KT: {"kt"},
}

# ---- KT: videos labelled [KT Karaoke] / [KT Sing Along] ("Artist - Title [KT Karaoke].mp4") ---
KT_MARK = re.compile(r"\[KT (?:Karaoke|Sing Along)\]", re.I)

# ---- duets ------------------------------------------------------------------------------
# Karaoke makers mark duet tracks: "(Duet)", "[Duet]", "(Mf Duet)", "Duet With".
DUET_MARK = re.compile(r"\bduet\b", re.I)
# Two singers credited together: "Kenny Rogers & Dolly Parton", "Johnny Cash With June Carter".
TWO_SINGERS = re.compile(r"\S\s+(?:&|and|with|duet with|\+)\s+\S", re.I)
# Bands and duos with "&" in the name that aren't duets: "Tom Petty & The Heartbreakers",
# "Mumford & Sons", and band names that are the whole first part ("Brooks & Dunn",
# "Simon & Garfunkel"). Only the first part counts, so "Garth Brooks & Trisha Yearwood"
# and "Diana Ross & Lionel Richie" are still duets.
NOT_A_DUET = re.compile(
    r"[&+]\s*(?:the|his|her|sons|friends|co)\b|\band\s+the\b|\bwith\s+the\b"
    r"|^\s*(?:the\s+)?(?:earth,? wind|kool|brooks|hall|simon|crosby,? stills|emerson,? lake|blood,? sweat|"
    r"peter,? paul|kc|sly|big|maddie|dan|love|montgomery gentry)\s*(?:&|\+|,|\band\b)", re.I
)

# ---- kids -------------------------------------------------------------------------------
# Disc brands and labels (the [...] tag in the file name, or anywhere).
KIDS_BRANDS = re.compile(r"\b(?:disney|kidz? ?bop|kids|children'?s|nickelodeon|nick jr|sesame|sing ?along kids)\b", re.I)
# Kids' artists, films and shows - matched against the artist part, not the song title.
KIDS_ARTISTS = re.compile(
    r"\b(?:kidz bop|raffi|barney|nursery rhymes|children'?s songs|kids songs|the wiggles|wiggles|sesame street|elmo|big bird|muppets?|"
    r"alvin and the chipmunks|the chipmunks|chipmunks|veggie ?tales|cocomelon|pinkfong|baby shark|"
    r"peppa pig|paw patrol|bluey|spongebob|pokemon|pokémon|dora|caillou|teletubbies|"
    r"frozen|moana|encanto|tangled|zootopia|aladdin|lion king|little mermaid|beauty and the beast|"
    r"mulan|pocahontas|hercules|tarzan|toy story|cinderella|snow white|sleeping beauty|pinocchio|"
    r"jungle book|winnie the pooh|101 dalmatians|lady and the tramp|mary poppins|the aristocats|"
    r"peter pan|bambi|dumbo|trolls|shrek|minions|despicable me|sing 2|sing movie|madagascar|"
    r"ice age|the incredibles|monsters inc|finding nemo|inside out|the greatest showman|"
    r"high school musical|hannah montana|descendants|camp rock|wizards of waverly place|"
    r"sound of music|wizard of oz|matilda|willy wonka|charlie and the chocolate factory)\b", re.I
)
# Nursery and children's songs, by title.
KIDS_SONGS = re.compile(
    r"^(?:twinkle,? twinkle,? little star|itsy bitsy spider|incy wincy spider|old macdonald|"
    r"the wheels on the bus|wheels on the bus|baby shark|abc song|the alphabet song|"
    r"head,? shoulders,? knees and toes|if you'?re happy and you know it|mary had a little lamb|"
    r"row,? row,? row your boat|rubber duckie|bingo|five little (?:ducks|monkeys)|"
    r"the hokey pokey|hokey pokey|london bridge|humpty dumpty|hickory dickory dock|"
    r"baa,? baa,? black sheep|this old man|the ants go marching|do your ears hang low|"
    r"the itsy bitsy spider|you are my sunshine|happy birthday(?: to you)?$|the alphabet|it'?s a small world|"
    r"bob the builder|the muffin man|pop goes the weasel|i'?m a little teapot|skidamarink)\b", re.I
)

BRACKETS = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")


def split_display(artist: str, title: str, display_name: str) -> tuple[str, str]:
    """(artist part, song title) from a library row's fields."""
    if " - " in (display_name or ""):
        left, right = display_name.split(" - ", 1)
        # Disc-code rows: "CBD-106894 - Garth Brooks (MPX) - Friends In Low Places"
        if re.fullmatch(r"[A-Z]{1,6}[\s-]*\d[\w-]*", left.strip(), re.I) and " - " in right:
            left, right = right.split(" - ", 1)
        return left, right
    return artist or "", title or display_name or ""


def tags_for(artist: str, title: str, display_name: str, file_name: str = "") -> list[str]:
    """Labels for one library song, e.g. ["duet"] or ["kids"]."""
    artist_part, song = split_display(artist, title, display_name)
    everything = " ".join(filter(None, [artist, title, display_name, file_name]))
    plain_artist = BRACKETS.sub("", artist_part).strip()
    plain_song = BRACKETS.sub("", song).strip()
    tags = []
    if DUET_MARK.search(everything) or (TWO_SINGERS.search(plain_artist) and not NOT_A_DUET.search(plain_artist)):
        tags.append(DUET)
    brand_tags = " ".join(re.findall(r"\[([^\]]*)\]", everything))
    if KIDS_BRANDS.search(brand_tags) or KIDS_ARTISTS.search(plain_artist) or KIDS_SONGS.search(plain_song):
        tags.append(KIDS)
    if KT_MARK.search(everything):
        tags.append(KT)
    return tags


def search_words(tags: list[str]) -> str:
    """Extra words for the search index, so "duets" or "kids" finds the song."""
    return " ".join(sorted(word for tag in tags for word in SEARCH_WORDS.get(tag, ())))


def split_query(normalized_query: str) -> tuple[set[str], str]:
    """({labels asked for}, the rest of the query): "duets dolly" -> ({"duet"}, "dolly")."""
    wanted, rest = set(), []
    for word in normalized_query.split():
        tag = next((t for t, words in SEARCH_WORDS.items() if word in words), None)
        if tag:
            wanted.add(tag)
        else:
            rest.append(word)
    return wanted, " ".join(rest)
