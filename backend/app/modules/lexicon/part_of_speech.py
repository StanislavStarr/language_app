from app.modules.lexicon.enums import PartOfSpeech

ALIASES = {
    "adjective": PartOfSpeech.ADJECTIVE,
    "adverb": PartOfSpeech.ADVERB,
    "pronoun": PartOfSpeech.PRONOUN,
    "preposition": PartOfSpeech.PREPOSITION,
    "conjunction": PartOfSpeech.CONJUNCTION,
    "determiner": PartOfSpeech.DETERMINER,
    "article": PartOfSpeech.DETERMINER,
    "interjection": PartOfSpeech.INTERJECTION,
    "exclamation": PartOfSpeech.INTERJECTION,
    "numeral": PartOfSpeech.NUMERAL,
    "number": PartOfSpeech.NUMERAL,
    "proverb": PartOfSpeech.PHRASE,
    "prep_phrase": PartOfSpeech.PHRASE,
    "adv_phrase": PartOfSpeech.PHRASE,
}

UNIVERSAL_TO_PART_OF_SPEECH = {
    "NOUN": PartOfSpeech.NOUN,
    "PROPN": PartOfSpeech.NOUN,
    "VERB": PartOfSpeech.VERB,
    "AUX": PartOfSpeech.VERB,
    "ADJ": PartOfSpeech.ADJECTIVE,
    "ADV": PartOfSpeech.ADVERB,
    "PRON": PartOfSpeech.PRONOUN,
    "ADP": PartOfSpeech.PREPOSITION,
    "CCONJ": PartOfSpeech.CONJUNCTION,
    "SCONJ": PartOfSpeech.CONJUNCTION,
    "DET": PartOfSpeech.DETERMINER,
    "INTJ": PartOfSpeech.INTERJECTION,
    "NUM": PartOfSpeech.NUMERAL,
    "PART": PartOfSpeech.PARTICLE,
}


def to_part_of_speech(name: str) -> PartOfSpeech:
    normalized = name.strip().lower()
    if normalized in ALIASES:
        return ALIASES[normalized]
    try:
        return PartOfSpeech(normalized)
    except ValueError:
        return PartOfSpeech.OTHER
