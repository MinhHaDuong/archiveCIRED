# Worklist — téléverser les vrais PDF dans Zotero My Library

Généré par `src/audit_pdf_stubs.py`. Données : `pdf_stub_worklist.json`.

## Constat

- Notices top-level : **764**
- Attachements `imported_file` : 683
- PDF réellement téléversés (`md5`) : **15**
- Coquilles vides (stubs sans fichier) : **668** (dont 642 copiés du groupe 329932, 404)

## Récupérables depuis l'archive physique

- Appariés au nom exact : **640**
- Appariés par radical (extension différente) : 7
- Introuvables (à normaliser) : **21**

### Ventilation par fonds (appariés)

| Fonds | PDF à téléverser |
|---|---|
| AUTRE | 29 |
| CIR_GEN | 10 |
| CIR_GOD | 54 |
| CIR_HOU | 9 |
| CIR_SAC | 385 |
| LEESU | 160 |

## Reproduire

```bash
uv run python src/audit_pdf_stubs.py  # réseau + creds Zotero requis
```
