from enum import StrEnum


class LexemeType(StrEnum):
    WORD = "word"
    PHRASE = "phrase"


class LexiconSource(StrEnum):
    WIKTIONARY = "wiktionary"
    FREE_DICTIONARY = "free_dictionary"
    AI = "ai"


class TranslationSource(StrEnum):
    WIKTIONARY = "wiktionary"
    AI = "ai"


class PartOfSpeech(StrEnum):
    NOUN = "noun"
    VERB = "verb"
    ADJECTIVE = "adj"
    ADVERB = "adv"
    PRONOUN = "pron"
    PREPOSITION = "prep"
    CONJUNCTION = "conj"
    DETERMINER = "det"
    INTERJECTION = "intj"
    NUMERAL = "num"
    PARTICLE = "particle"
    PHRASE = "phrase"
    OTHER = "other"


class MeaningContentStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"
