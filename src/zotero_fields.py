"""Garde partagée : champs Zotero valides selon l'itemType.

Zotero refuse (HTTP 400) `publicationTitle` hors `journalArticle` : le même
champ de base s'appelle `proceedingsTitle` (conferencePaper) ou `bookTitle`
(bookSection). Les écrire sous ces noms est hors périmètre ; on s'abstient.
"""

PUBLICATION_TITLE_TYPES = frozenset({"journalArticle"})


def allows_publication_title(item_type: str | None) -> bool:
    """Vrai si `publicationTitle` est un champ valide pour cet itemType."""
    return item_type in PUBLICATION_TITLE_TYPES
