# Image Viewer – suunnitelma

**Tekijä:** Elias
**Kansio:** `frontend/src/viewer/`
**Branch:** `feature/image-viewer`
**Deadline:** su 15.11.2026 klo 23.59
**Pohja:** [CONTRACT.md](../../../CONTRACT.md) ja tiimin ohjeet
**Tekniikka:** React + TypeScript (Vite), ei vielä lopullisesti varmistettu

## 1. Tavoite
Käyttäjä näkee valitsemansa taivaan kohdan SPHEREx-kuvat peräkkäin animaationa epookista toiseen. Liikkuva kohde, kuten lähitähti tai ruskea kääpiö, erottuu silloin silmällä.

Kohteen voi valita kolmella tavalla:
- klikkaamalla Aladin Lite -karttaa
- syöttämällä koordinaatit
- valitsemalla valmiin kohteen

Kaikki kolme päätyvät samaan `setTarget(ra, dec, fov)`-kutsuun. Kartta ja syöttökenttä ovat Juhon osuutta, joten viewerin ei tarvitse tietää, mistä koordinaatit tulivat.

```
Aladin-kartta / syöttö (Juho)  →  RA/Dec
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
- **Lataus:** vaihe (`stage`) ja edistyminen `done/total`. Tämä on tärkeä, koska kartan klikkaus osuu yleensä kohtaan, jota ei ole välimuistissa.
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

## 4. Komponentit

| Tiedosto | Tehtävä |
|---|---|
| `Viewer.tsx` | julkinen komponentti, joka kokoaa osat ja pitää tilan (kaista, epookki, toisto, diff, filtterit) |
| `BlinkImage.tsx` | kuva ja SVG-kerros |
| `PlaybackControls.tsx` | kaikki ohjaimet |
| `EpochInfo.tsx` | epookin päivämäärä ja kuvien määrä |
| `CursorInfo.tsx` | pikseli, RA ja Dec hiiren kohdalla |
| `skyCoords.ts` | pikselin muunnos RA/Dec-koordinaateiksi |
| `SpectrumChart.tsx` | spektrikaavio |
| `StatusView.tsx` | tyhjä-, lataus- ja virhetila |
| `useBlink.ts` | toiston ajastus (hook) |
| `parseSpectrum.ts` | CSV:n lukeminen |
| `types.ts` | `Meta`-tyyppi CONTRACTin mukaan |

`viewer/` ja `app/` eivät importtaa toisiaan. Ne kommunikoivat vain `state.ts`:n ja `api/`:n kautta.

## 5. Rajapinta Juholle (ehdotus)

```tsx
<Viewer status={{ kind: "empty" }} />
<Viewer status={{ kind: "loading", stage, done, total }} />
<Viewer status={{ kind: "done", meta, baseUrl }} />
<Viewer status={{ kind: "error", message }} />
```

Viewer ei kutsu API:a itse. App tai `api/` hoitaa pollauksen ja sen keskeyttämisen, ja viewer vain näyttää tilan.

## 6. Työjärjestys

| # | Työ | Valmis kun |
|---|---|---|
| 1 | Blink, kaistan valinta, play/pause ja epookin tiedot mock-datalla | Barnardin tähti näkyy liikkuvan noin 1,7 px pohjoiseen |
| 2 | Erotuskuva, nopeus, askellus, kirkkaus ja kontrasti sekä koordinaatit hiiren kohdalla | kaikki ohjaimet toimivat ja Barnardin tähden kohdalla näkyy sen koordinaatit |
| 3 | Tyhjä-, lataus- ja virhetila sekä kytkentä Juhon appiin | kartan klikkaus näyttää kuvat oikealta backendiltä |
| 4 | Spektrikaavio | kaavio näkyy virhepalkkeineen |
| 5 | Gaia-ympyrät (jos aikaa jää) | ympyrät osuvat tähteen joka epookissa |

Jokaisen vaiheen jälkeen tehdään commit (`feat(viewer): …`) ja merge mainiin. Mainin pitää aina buildata.

## 7. Avoimet asiat
- [ ] Varmistuuko React?
- [ ] Kuka tekee Vite-pohjan ja kopioi mock-datan (`examples/barnard/` → `public/mock/barnard/`)?
- [ ] Propsien muoto pitää sopia Juhon kanssa.
- [ ] Missä viewer näkyy suhteessa isoon Aladin-karttaan (vieressä, päällä ikkunana vai alla) ja miten se toimii mobiilissa?
- [ ] Klikatun kohdan merkki kartalle (Juho).
- [ ] Spektrikaavion kirjasto: Chart.js (`react-chartjs-2` ja error bar -plugin) vai uPlot.
- [ ] Gaia-sijainnit: Emililtä uutena `meta.json`-avaimena (katso `science/gaia_validation.py`) vai suoraan Gaiasta?
- [ ] CORS backendissä, jos frontend ja backend ovat eri osoitteissa (Erik).
