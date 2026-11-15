# Image Viewer – suunnitelma

**Tekijä:** Elias
**Kansio:** `frontend/src/viewer/`
**Branch:** `feature/image-viewer`
**Deadline:** su 15.11.2026 klo 23.59
**Pohja:** [CONTRACT.md](../../../CONTRACT.md) ja tiimin ohjeet
**Tekniikka:** React + TypeScript (Vite), ei vielä lopullisesti varmistettu

## 1. Tavoite
Käyttäjä näkee valitsemansa taivaan kohdan SPHEREx-kuvat peräkkäin animaationa epookista toiseen. Liikkuva kohde, kuten lähitähti tai ruskea kääpiö, erottuu silloin silmällä.

Kohteen voi valita kahdella tavalla:
- syöttämällä koordinaatit
- valitsemalla valmiin kohteen

Molemmat päätyvät samaan `setTarget(ra, dec, fov)`-kutsuun. Syöttökenttä ja kohdelista ovat Juhon osuutta, joten viewerin ei tarvitse tietää, mistä koordinaatit tulivat. Aladin Lite -karttaa ei käytetä.

```
Syöttö / kohdelista (Juho)  →  RA/Dec
   →  setTarget(ra, dec, fov)    (state.ts)
   →  /api/sky + pollaus         (api/)
   →  Viewer näyttää kuvat       (Elias)
```

## 2. Ominaisuudet

### Päänäkymä
- Valitun kaistan epookit vaihtuvat peräkkäin (blink).
- Kuva näytetään `<img>`-elementtinä, CSS:nä `image-rendering: pixelated`.
- Kuvan päällä on SVG-kerros, jonka `viewBox="0 0 31 31"` vastaa SPHEREx-pikseleitä.
- Canvasia ei käytetä. Sitä harkitaan vain, jos science alkaa tuottaa raakadataa pikselitason venytystä varten.

### Ohjaimet
- play/pause
- nopeus
- askellus kuva kerrallaan eteen ja taakse
- kirkkaus ja kontrasti (CSS `filter`)
- kaistan valinta: ALL, D1–D6
- erotuskuva päälle ja pois (`diff_<band>.png`)

### Tiedot kuvan alla
- epookin päivämäärä (`epochs[i].date`)
- kuvien määrä (`detectors[band].n_images`, ALL-kaistalla `n_images`)

### Koordinaatit hiiren kohdalla
- Kun hiiri on kuvan päällä, kuvan alla näkyy pikseli sekä RA ja Dec, esimerkiksi `Pikseli (15, 12)  RA 269.4461°  Dec 4.7707°`.
- Lasketaan hiiren paikasta, kuvan keskipisteestä (`ra_deg`, `dec_deg`) ja pikselikoosta (`pixel_scale_arcsec`). Canvasia ei tarvita.
- Keskipikseli on (15, 15). Pohjoinen on ylhäällä ja itä vasemmalla, joten:
  - `dec = dec_deg - (y - 15) * scale / 3600`
  - `ra = ra_deg - (x - 15) * scale / 3600 / cos(dec_deg)`
- Mobiilissa sama tieto näytetään napautuksesta.
- Vuota (MJy/sr) hiiren kohdalla ei näytetä, koska PNG:istä saa vain harmaasävyn 0–255. Se vaatisi raakadataa Emililtä.

### Spektrikaavio (`spectrum.csv`)
- x on `wavelength_um`, y on `flux_mjy_sr`
- virhepalkit kentästä `err_mjy_sr`
- värit epookin mukaan

### Tilat
- **Tyhjä:** kohdetta ei ole vielä valittu.
- **Lataus:** vaihe (`stage`) ja edistyminen `done/total`. Tämä on tärkeä, koska omat koordinaatit osuvat yleensä kohtaan, jota ei ole välimuistissa.
- **Virhe:** selkeä viesti, esimerkiksi "No SPHEREx images cover this position".
- **Uusi kohde kesken latauksen:** viewer siirtyy suoraan uuteen kohteeseen, eikä edellisen kohteen kuvia saa jäädä näkyviin.

### Myöhemmin
- Gaia-tähdet ympyröinä SVG-kerroksella siinä paikassa, jossa ne olivat kunkin epookin aikaan.

## 3. Säännöt datan käsittelyyn
- Epookin numero luetaan tiedostonimestä (`epoch3.png` → `meta.epochs[3]`), ei listan järjestyksestä. Kaistoilla on eri epookit, esimerkiksi D2:lla vain 0, 2 ja 4.
- Polut ovat suhteessa `base_url`:iin: `base_url + outputs[band].frames[i]`.
- Tuntemattomat avaimet `meta.json`:ssa ohitetaan.
- `flagged_frac`-kenttää ei näytetä käyttäjälle, koska sen arvo on toistaiseksi aina 1.0.
- Ristikko ja otsikko ovat jo kuvissa, joten niitä ei piirretä itse.
- Kuvat ovat 372×372 px (31×31 SPHEREx-pikseliä 12× suurennettuna), pohjoinen ylhäällä ja itä vasemmalla. Pikselikoko on 6,15″.

### Tiedossa olevat science-ongelmat (eivät viewerin bugeja)
- Kirkkaiden tähtien ytimet näkyvät mustina joissain kuvissa (esimerkiksi ALL epoch1 ja D1 epoch0).
- `flagged_frac` on 1.0 kaikkialla.
- Spektri mitataan kuvan keskeltä, joten varhaisissa epookeissa liikkuvan tähden vuo jää liian pieneksi.

## 4. Rakenne

### Näkymä

```
┌──────────────────────────────────────────────┐
│  Barnard's Star                              │  ← otsikko
│            ┌──────────────────┐              │
│            │  kuva + SVG      │              │  ← BlinkImage
│            └──────────────────┘              │
│  Epoch 3/5 · 2026-02-08 · 10 images          │  ← EpochInfo
│  Pixel (15,12) · RA 269.4461° · Dec 4.7707°  │  ← CursorInfo
├──────────────────────────────────────────────┤
│  [ALL] [D1] … [D6]                           │  ← PlaybackControls
│  ◀  Pause  ▶   speed ──●──   [Difference]    │
│  brightness ──●──   contrast ──●──           │
├──────────────────────────────────────────────┤
│  Spectrum                                    │  ← SpectrumChart
│  Data: NASA/IPAC IRSA, SPHEREx Team          │  ← credit
└──────────────────────────────────────────────┘
```

Tyhjä-, lataus- ja virhetilassa koko alue korvataan `StatusView`-näkymällä. Käyttöliittymän tekstit ovat englanniksi.

### Tiedostot

```
viewer/
├── index.ts              # ainoa tiedosto, jota muu sovellus importtaa
├── Viewer.tsx            # julkinen komponentti ja viewerin tila
├── types.ts              # Meta, Epoch, Frame, ViewerStatus
├── viewer.css
├── components/
│   ├── BlinkImage.tsx    # kuvapino, SVG-kerros, hiiren pikseli
│   ├── EpochInfo.tsx     # päivämäärä ja kuvien määrä
│   ├── CursorInfo.tsx    # pikseli, RA ja Dec
│   ├── PlaybackControls.tsx  # kaista, toisto, nopeus, diff, kirkkaus, kontrasti
│   ├── SpectrumChart.tsx # SVG-kaavio: virhepalkit, värit epookin mukaan, D1–D6
│   └── StatusView.tsx    # tyhjä, lataus, virhe
├── hooks/
│   └── useBlink.ts       # toiston ajastus
└── lib/
    ├── frames.ts         # kuvat kaistalle, epookin numero tiedostonimestä
    ├── skyCoords.ts      # pikseli → RA/Dec
    ├── parseSpectrum.ts  # spectrum.csv → rivit
    ├── chartScale.ts     # akselit ja asteikot käsin piirrettyyn kaavioon
    └── stage.ts          # backendin vaiheen nimi → teksti käyttäjälle
```

### Periaatteet
- **Komponentit vain näyttävät.** Laskenta on kansiossa `lib/`, jossa on pelkkiä funktioita. Ne voi testata ilman Reactia.
- **Muu sovellus näkee vain `index.ts`:n**, joten sisäistä rakennetta voi muuttaa vapaasti.
- **Tila on yhdessä paikassa**, `Viewer.tsx`:ssä. Se kulkee alas propseina, ja muutokset tulevat ylös callbackeina.
- **Uusi kohde nollaa kaiken.** Ladattu viewer saa `key={baseUrl}`, joten React luo sen alusta, kun kohde vaihtuu.
- **Kaikki kaistan kuvat ovat sivulla koko ajan**, ja vain yksi näkyy. Blink ei siksi odota latausta.
- **Kosketusnäytöllä** viimeisin napautus jää näkyviin `CursorInfo`:on.

### Viewerin tila

| Tila | Alkuarvo | Huomio |
|---|---|---|
| `band` | ensimmäinen kaista, jolla on kuvia (yleensä `ALL`) | vaihto nollaa `frameIdx`:n |
| `frameIdx` | `0` | indeksi kaistan kuvalistaan, **ei** epookin numero |
| `playing` | `true` | askellus pysäyttää toiston |
| `fps` | `2` | 0,5–10 |
| `showDiff` | `false` | erotuskuvan aikana toisto on pois päältä |
| `brightness`, `contrast` | `1`, `1` | CSS `filter`, 0,2–3 |
| `hoverPx` | `null` | hiiren tai napautuksen pikseli |

`viewer/` ja `app/` eivät importtaa toisiaan. Ne kommunikoivat vain `state.ts`:n ja `api/`:n kautta.

## 5. Rajapinta Juholle (ehdotus)

```tsx
<Viewer status={{ kind: "empty" }} />
<Viewer status={{ kind: "loading", stage, done, total }} />
<Viewer status={{ kind: "loading", stage, done, total, preview: { meta, baseUrl } }} />
<Viewer status={{ kind: "done", meta, baseUrl }} />
<Viewer status={{ kind: "error", message }} />
```

- `baseUrl` on täydellinen osoite: `API + base_url` (Erikin `fileUrl`-mallin mukaan).
- `preview` on valinnainen. Kun backendin `/api/status` palauttaa `preview`-kentän, app välittää sen sellaisenaan. Viewer näyttää silloin esikatselukuvat, ja niiden yläpuolella on edistymispalkki. Kun täysi tulos tulee, kaista, kuva ja säädöt säilyvät, koska kohde on sama.
- `stage` välitetään sellaisenaan, myös `preview_`-etuliitteellä. Viewer muuttaa sen luettavaksi tekstiksi.

Viewer ei kutsu API:a itse. App tai `api/` hoitaa pollauksen ja sen keskeyttämisen, ja viewer vain näyttää tilan.

Käyttö appissa:

```tsx
import { Viewer, type ViewerStatus } from "../viewer";
```

## 6. Työjärjestys

**Tilanne:** rakenne on valmis. Kuvapino, ohjaimet, epookin tiedot, koordinaatit, tilat ja CSV:n lukeminen on kirjoitettu. Myös spektrikaavio on valmis. Se on piirretty SVG:llä ilman kirjastoa, joten `package.json`:iin ei tarvita uusia paketteja.

**Spektrikaavio:**
- x on aallonpituus (µm) ja y vuo (MJy/sr), virhepalkkien kanssa. Y-akseli alkaa nollasta, ellei vuo mene sen alle.
- Värit epookin mukaan, ja selite näyttää päivämäärät.
- Ilmaisinalueet D1–D6 näkyvät taustalla vuorottaisina raitoina.
- Blinkissä näkyvän epookin pisteet korostetaan ja muut himmennetään. Erotuskuvan aikana kaikki näkyvät tasavahvoina.
- Hiiri tai napautus näyttää lähimmän pisteen arvon.
- Akselit tarkistettu kaikilla 5 kohteella: jokainen piste virhepalkkeineen mahtuu piirtoalueelle.

Juhon frontend on branchissa `front-end`. Viewer kääntyy sen kanssa (React 19, TypeScript 7, Vite 8).

**Testaus ennen pohjaa:** Node on asennettu. Erillinen Vite + React -testiympäristö (repon ulkopuolella) ajaa viewerin lähdekoodia Erikin julkaistua API:a vasten: `https://planetx-api-38053485414.us-east4.run.app`. Testatut tapaukset: 5 haastekohdetta, vapaa koordinaatti (M31), virheellinen syöte ja simuloitu esikatseluajo. TypeScriptin tiukka tarkistus menee läpi.

**Havaintoja oikeasta API:sta (14.11.2026):** uusi koordinaatti kesti noin 7,5 minuuttia. Esikatselu tuli noin 3,5 minuutissa, ja `processing 36/36` kesti noin 3 minuuttia. Siksi täysi palkki näytetään vain, kun laskuri liikkuu; muuten palkki on epämääräinen.

| # | Työ | Valmis kun |
|---|---|---|
| 1 | Blink, kaistan valinta, play/pause ja epookin tiedot mock-datalla | Barnardin tähti näkyy liikkuvan noin 1,7 px pohjoiseen |
| 2 | Erotuskuva, nopeus, askellus, kirkkaus ja kontrasti sekä koordinaatit hiiren kohdalla | kaikki ohjaimet toimivat ja Barnardin tähden kohdalla näkyy sen koordinaatit |
| 3 | Tyhjä-, lataus- ja virhetila sekä kytkentä Juhon appiin | syötetyt koordinaatit näyttävät kuvat oikealta backendiltä |
| 4 | Spektrikaavio | kaavio näkyy virhepalkkeineen |
| 5 | Gaia-ympyrät (jos aikaa jää) | ympyrät osuvat tähteen joka epookissa |

Jokaisen vaiheen jälkeen tehdään commit (`feat(viewer): …`) ja merge mainiin. Mainin pitää aina buildata.

## 7. Yhteensopivuus Emilin datan kanssa

Tarkistettu `fetch_spherex.py`:n tuottamaa `meta.json`:ia vasten (14.11.2026).

**Täsmää:**
- Kaikki viewerin lukemat avaimet ovat olemassa.
- Tiedostonimet ovat muotoa `frames/{band}/epoch{e}.png`.
- Kuvat ovat aina neliöitä ja koko pariton (31, tai 99 suurimmalla 10′ kentällä), joten keskipikseli on olemassa.
- Otsikkoteksti piirretään kuvan päälle, joten pikselien paikat eivät siirry.
- Kaistat, joilla on yksi kuva, eivät saa erotuskuvaa eivätkä GIFiä. Viewer poistaa silloin toiston ja diff-napin käytöstä.
- Uudet avaimet (`lightcurve`, `gaia_validation`, `outputs[band].fits`) ohitetaan.
- Gaia-merkkiä ei polteta kuviin oletuksena, vaan viewer piirtää sen SVG-kerrokseen (Emilin koodin kommentti).

**Huomioitavaa:**
- `base_url` on suhteellinen polku (`/api/files/<job>/`). `api/`-kansion pitää lisätä API:n osoite eteen ennen kuin `baseUrl` annetaan viewerille.
- WISE 0855:n kuvat ovat negatiivina, eikä `meta.json` kerro sitä. Erotuskuva ei ole käännetty.
- Gaia-sijainti tulee avaimesta `gaia_validation.pixel_coords` (`canvas_x`, `canvas_y`). Se on vain viimeiselle epookille, ja SVG:ssä siihen lisätään 0,5, jotta ympyrä osuu pikselin keskelle.
- Otsikkopalkki (16 px) peittää kuvan yläreunan: noin 1,3 pikseliriviä 31 px kuvassa, noin 4 riviä 10′ kentällä.
- Donitsit (mustat kyllästyneet ytimet) ovat science-puolen ongelma, jota korjataan.

## 8. Avoimet asiat
- [ ] Varmistuuko React?
- [ ] Kuka tekee Vite-pohjan ja kopioi mock-datan (`examples/barnard/` → `public/mock/barnard/`)?
- [ ] Propsien muoto pitää sopia Juhon kanssa.
- [ ] Viewerin paikka sivulla ja toiminta mobiilissa (Juho).
- [x] Spektrikaavio: piirretty SVG:llä, ei kirjastoa.
- [ ] R Draconiksen spektrin vuo on lähes nolla (−0,0…0,1 MJy/sr), vaikka kohde on kirkas Mira-muuttuja. Kyllästyminen? (Emil)
- [ ] Gaia-sijainnit: Emililtä uutena `meta.json`-avaimena (katso `science/gaia_validation.py`) vai suoraan Gaiasta?
- [x] CORS backendissä (Erik): kaikki osoitteet sallittu.
- [ ] `api/` tekee `baseUrl`:sta täydellisen osoitteen ja välittää `preview`-kentän (Juho).
- [ ] Pollaus yrittää uudelleen, jos yksittäinen `/api/status` epäonnistuu. Palvelin oli testissä noin minuutin vastaamatta, vaikka haku jatkui (Juho/Erik).
- [ ] Vapaan koordinaatin Gaia-haku palauttaa `QUERY_ERROR` (Emil).
- [ ] Avain `"inverted": true` käännetyille kuville, jotta viewer voi kertoa sen käyttäjälle (Emil).
- [ ] Valokäyrä (`lightcurve.csv`) samaan kaavioon kuin spektri? Hyödyllinen muuttuville tähdille (RW Aur, R Dra).
