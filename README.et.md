# Smart Energy Scheduler Home Assistantile

[![Validate](https://github.com/rihokirss/ha-smart-energy-scheduler/actions/workflows/validate.yml/badge.svg)](https://github.com/rihokirss/ha-smart-energy-scheduler/actions/workflows/validate.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://www.hacs.xyz/)
[![Home Assistant 2026.8+](https://img.shields.io/badge/Home%20Assistant-2026.8%2B-18BCF2.svg)](https://www.home-assistant.io/)

🇬🇧 **English:** [README.md](README.md)

Smart Energy Scheduler on Home Assistanti kohandatud integratsioon, mis planeerib
soojuspumpade, boilerite, elektriauto laadimisloa ja teiste lülitatavate seadmete töö
ajale, mil elekter on kõige soodsam.

Integratsioon koondab Nord Pooli järgmise päeva börsihinnad, ostu- ja müügitasud,
võrgutasud, Forecast.Solari päikeseprognoosi, maja baaskoormuse ja valikulise
ilmapõhise juhtimise jooksvaks 48 tunni plaaniks. Iga juhitav seade jääb tavaliseks Home
Assistanti olemiks ning seda saab jälgida ja käsitsi juhtida loodud olemite või kaasasolevate
Lovelace'i kaartide kaudu.

> [!CAUTION]
> Integratsioon saadab päris `turn_on` ja `turn_off` käske. Hoia **varirežiim** sees seni,
> kuni oled oma paigalduses üle kontrollinud tariifid, seadme tagasiside, veaolukorra
> käitumise ja koostatud plaanid.

## Võimalused

- Jooksev 48 tunni plaan Nord Pooli järgmise päeva hindade põhjal.
- Iga seadme jaoks eraldi plaan.
- Seadme käivitused 15- või 60-minutilise sammuga.
- Päevased baas-, miinimum- ja maksimumtunnid.
- Minimaalsed järjestikused ON- ja OFF-ajad.
- Valikulised efektiivhinna piirid „alati sees“ ja „alati väljas“.
- Kütteseadmete tööaeg ilmaprognoosi järgi (küttekõver).
- Forecast.Solari tugi Home Assistanti energiapaneeli kaudu.
- Päikeseenergia jagatakse seadmete vahel prioriteedi järgi nii, et sama toodangut ei
  arvestata kaks korda.
- Päikesetõusu ja -loojangu põhine varuplaan, kui päikeseprognoos puudub.
- Valikuline talveperiood, mil päikeseenergiat ei arvestata, näiteks 15. oktoober – 15.
  veebruar.
- Käibemaks, ostu- ja müügimarginaal, päeva- ja öötariif, nädalavahetused ja riigipühad.
- Varirežiim, valitav käitumine andmevea korral, pööratud väljund ja ajastatud käsijuhtimine.
- Sensorid, juhtelemendid, teenused, WebSocketi uuendused ja kolm Lovelace'i kaarti.
- Seadistus eesti ja inglise keeles.

## Nõuded

| Nõue | Milleks |
| --- | --- |
| Home Assistant 2026.8.0 või uuem | Alamkirjed (config subentries) ja praegused seadistusvoogude API-d |
| [HACS](https://hacs.xyz/) (soovitatav) | Integratsiooni paigaldamine ja uuendamine |
| [Nord Pooli kohandatud integratsioon](https://github.com/custom-components/nordpool) | Börsihinnad selle `nordpool.hourly` teenuse kaudu |
| `switch`, `input_boolean` või `light` olem | Juhitav seade või selle tööluba |
| Tunnipõhise prognoosiga `weather` olem (valikuline) | Ilmapõhine tööaeg |
| Energiapaneelis seadistatud Forecast.Solar (valikuline) | Päikesetoodangu prognoos |

Home Assistanti sisseehitatud Nord Pooli integratsioonil puudub `nordpool.hourly` teenus,
seega paigalda kohandatud integratsioon allpool kirjeldatud viisil. Integratsioon eeldab, et
Nord Pooli vastuses on veerandtunnised hinnad. Homsed hinnad pole kohustuslikud enne, kui
pakkuja on avaldanud terve kohaliku päeva hinnad.

## Paigaldamine

Menüüde nimed on toodud nii, nagu need on Home Assistanti ingliskeelses ja (sulgudes)
eestikeelses kasutajaliideses.

### 1. Paigalda Nord Pooli kohandatud integratsioon

Hinnad loetakse [Nord Pooli kohandatud integratsiooni](https://github.com/custom-components/nordpool)
`nordpool.hourly` teenusest. Jäta see samm vahele, kui **Settings → Tools → Actions**
(*Seaded → Tööriistad → Toimingud*) all on `nordpool.hourly` juba olemas.

[![Ava Nord Pooli repo HACS-is.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=custom-components&repository=nordpool&category=integration)

1. Paigalda [HACS](https://hacs.xyz/docs/use/), kui seda veel pole.
2. Otsi HACS-ist **Nord Pool**, ava see ja vali **Download**.
3. Taaskäivita Home Assistant: **Settings → System → ⏻ → Restart Home Assistant**
   (*Seaded → Süsteem → ⏻ → Taaskäivita Home Assistant*).
4. Ava **Settings → Devices & services → Add integration** (*Seaded → Seadmed ja teenused →
   Lisa sidumine*), vali **Nord Pool** ning määra hinnapiirkond (näiteks `EE`) ja valuuta.
5. Kontrolli, et `nordpool.hourly` on olemas menüüs **Settings → Tools → Actions**.

> [!NOTE]
> Kohandatud integratsioon kasutab sama `nordpool` domeeni nagu sisseehitatud Nord Pooli
> integratsioon ja asendab selle. Sisseehitatud integratsiooni olemasolevad kirjed tuleb
> kohandatud integratsiooniga uuesti luua.

### 2. Lisa see repo HACS-i

Repo pole veel HACS-i vaikekataloogis, seega lisa see kohandatud repona (custom repository).
Allolev nupp avab vastava akna otse:

[![Ava Smart Energy Scheduler HACS-is.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=rihokirss&repository=ha-smart-energy-scheduler&category=integration)

Või lisa see käsitsi:

1. Ava külgribalt **HACS**.
2. Ava paremal üleval kolme punkti menüü ja vali **Custom repositories**.
3. Sisesta väljale **Repository** `https://github.com/rihokirss/ha-smart-energy-scheduler`,
   vali **Type** väärtuseks **Integration** ja vajuta **Add**.
4. Sulge aken.

### 3. Laadi alla ja taaskäivita

1. Otsi HACS-ist **Smart Energy Scheduler** ja ava see.
2. Vali all paremal **Download** ja kinnita.
3. Taaskäivita Home Assistant.

### 4. Lisa integratsioon

[![Alusta Smart Energy Scheduleri seadistamist.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=smart_energy_scheduler)

Või ava **Settings → Devices & services → Add integration** (*Seaded → Seadmed ja teenused →
Lisa sidumine*) ja otsi **Smart Energy Scheduler**. Vormis:

1. Kontrolli Nord Pooli piirkonda, marginaale, käibemaksu ja võrgutasusid. Kõik hinnad on
   ühikus `EUR/MWh` (`1 s/kWh = 10 EUR/MWh`).
2. Vali tunnipõhise prognoosiga ilmaolem, kui kütteseadmed peavad ilma järgi töötama.
3. Jäta **Varirežiim** sisse.
4. Märgi **Olen tariifid üle kontrollinud** ja salvesta.

### 5. Seadista juhitav seade

Seadistamisel luuakse näidisseade nimega **Soojuspump**. Integratsiooni lehel
(**Settings → Devices & services → Smart Energy Scheduler**):

1. Vali **Soojuspump** realt **Configure device** (*Seadista seade*).
2. Vali oma `switch`, `input_boolean` või `light` olem ja vaata kõik sektsioonid üle.
3. Lisa teisi seadmeid, näiteks boiler, nupuga **Add controlled device** (*Lisa juhitav
   seade*).

### 6. Lisa Lovelace'i kaardid (valikuline)

1. Ava **Settings → Dashboards** (*Seaded → Vaated*), seejärel paremal üleval kolme punkti
   menüüst **Resources** (*Ressursid*).
2. Vali **Add resource** (*Lisa uus ressurss*), sisesta
   `/smart_energy_scheduler/smart-energy-scheduler-card.js`, vali tüübiks **JavaScript
   module** (*JavaScripti moodul*) ja salvesta.
3. Värskenda brauserit puhvrit tühjendades, muuda töölauda, lisa **Manual** kaart ja kleebi
   sinna mõni näide jaotisest [Lovelace'i kaardid](#lovelacei-kaardid).

### 7. Kontrolli varirežiimis ja lülita juhtimine sisse

Jälgi plaani vähemalt kaks päeva (vaata [Ohutus ja väljundi
käitumine](#ohutus-ja-väljundi-käitumine)). Kui plaan on mõistlik, vali integratsiooni kolme
punkti menüüst **Reconfigure** (*Seadista uuesti*) ja lülita **Varirežiim** välja.

### Käsitsi paigaldamine ilma HACS-ita

1. Laadi see repo alla või klooni see.
2. Kopeeri `custom_components/smart_energy_scheduler` Home Assistanti masinas kausta
   `<config>/custom_components/smart_energy_scheduler`.
3. Taaskäivita Home Assistant ja jätka [sammust 4](#4-lisa-integratsioon).

Lõpuks peab kaustas olema vähemalt:

```text
<config>/custom_components/smart_energy_scheduler/
├── __init__.py
├── config_flow.py
├── manifest.json
├── services.yaml
├── strings.json
├── translations/
└── frontend/
```

## Seadistamine

Toetatud on üks planeerija kirje. Täiendavad juhitavad seadmed luuakse alamkirjetena nupuga
**Add controlled device** (*Lisa juhitav seade*) integratsiooni lehel.

### Ühisseaded

Integratsiooni **Reconfigure** (*Seadista uuesti*) all on kõigile seadmetele ühised seaded:

- Nord Pooli piirkond ja valuuta;
- ostu- ja müügimarginaal;
- käibemaks ja kas võrgutasud sisaldavad juba käibemaksu;
- päevane ja öine võrgutasu ning tariifide kellaajad;
- öötariif nädalavahetustel ja riigipühadel;
- ilmaolem ja maja baaskoormus;
- päikese varuplaani kuud ning nihked päikesetõusu ja -loojangu suhtes;
- valikuline talveperiood, mil päikesetoodangut ei arvestata;
- valikulised võrgu- ja PV-võimsuse sensorid diagnostikaks;
- varirežiim ja tariifide kinnitus.

### Seadme seaded

Igal juhitaval seadmel on kuus kokkuklapitavat sektsiooni:

| Sektsioon | Seaded |
| --- | --- |
| Seade | Nimi, sihtolem, pööratud väljund, automaatjuhtimine |
| Tööaken ja tunnid | Tööaken, baas-, miinimum- ja maksimumtunnid, planeerimise samm, minimaalsed ON/OFF ajad |
| Võimsus ja mõõtmine | Tagasiside olem, võimsussensor, kordaja, nimivõimsus |
| Hinnapiirid | Valikulised „alati sees“ ja „alati väljas“ efektiivhinnad |
| Ilmapõhine juhtimine | Ilma arvestamine, referentstemperatuur, kõvera tõus, prognoosi aken ja ettevaade |
| Täpsem käitumine | Päikeseprioriteet ja käitumine andmevea korral |

Kui tööakna algus ja lõpp on samad, võib seade töötada terve päeva. 15-minutiline samm
lubab käivitusi kell `:00`, `:15`, `:30` ja `:45`, 60-minutiline samm ainult kell `:00`.
Väiksem samm ei lühenda minimaalseid ON/OFF aegu.

## Andmeallikad ja arvutusmudel

### Elektri hind

Iga turuintervalli efektiivne ostuhind arvutatakse nii:

```text
(börsihind + ostumarginaal) × (1 + käibemaks) + kehtiv võrgutasu
```

Kui **Võrgutasud sisaldavad käibemaksu** on sees, ei lisata võrgutasule käibemaksu.
Müügihind on:

```text
börsihind + müügimarginaal
```

Iga veerandtund tariifitakse oma kohaliku kellaaja järgi. Arvesse võetakse ka 23-, 24- ja
25-tunnised päevad, sealhulgas suveaja lõpus korduv tund. Puuduv või poolik järgmine päev ei
muuda tänast plaani kehtetuks; integratsioon proovib järgmisel uuendusel uuesti.

### Päikeseprognoos

Smart Energy Scheduler kasutab samu päikeseprognoosi allikaid, mis on valitud menüüs
**Settings → Dashboards → Energy → Solar production**. Ainult Forecast.Solari paigaldamisest
ei piisa: selle kirje peab olema energiapaneeli päikeseallika juures valitud prognoosi
pakkujaks.

Kui valitud on mitu pakkujat, liidetakse nende tunnipõhised `wh_hours` read. Prognoositud
PV katab esmalt maja baaskoormuse. Ülejäänud PV jagatakse juhitavatele seadmetele
päikeseprioriteedi järjekorras ainult üks kord, nii et sama toodangut ei arvestata kahele
seadmele. Omatarbeks kasutatud PV väärtus on müügitulu, mis oleks muidu saadud.

Kui kõik pakkujad puuduvad või ebaõnnestuvad, saab valikuline varuplaan eeldada
päikesetoodangut seadistatud kuudel päikesetõusu ja -loojangu vahel. Väljaspool seda akent on
toodang null ja planeerimine jätkub ainult hinna järgi koos hoiatusega. Valikuline
PV-võimsuse sensor on ainult diagnostikaks ja seda prognoosina ei kasutata.

Valikuline **talveperiood** jätab nii prognoosi kui ka varuplaani PV arvestamata igal
kohalikul päeval seadistatud esimese ja viimase kuu/päeva vahel, kaasa arvatud. Periood
võib ulatuda üle aastavahetuse, nii et `10/15` kuni `2/15` katab ajavahemiku 15. oktoobrist
15. veebruarini. Kui kogu planeerimisaken jääb talveperioodi, päikeseprognoosi ei pärita.
Kui tänane päev on perioodis, näitavad plaanikaardid sinist **TALVEREŽIIM** märki. Maja
baaskoormus ja hinnapõhine planeerimine ei muutu.

### Ilmapõhine juhtimine

Ilma järgi juhitava seadme päevane tööaeg on:

```text
baastunnid + (referentstemperatuur − prognoositud näiv temperatuur) × tunnid kraadi kohta
```

Tulemus ümardatakse ja piiratakse seadistatud miinimumi ja maksimumiga. Prognoosi väärtus
keskmistatakse seadistatava akna ulatuses ja seda akent saab hoone soojusinertsi jaoks
tulevikku nihutada.

Vana režiim arvutab tuulekülma prognoositud temperatuurist ja tuule kiirusest. Kui vana
režiim on väljas, eelistatakse pakkuja `apparent_temperature` väärtust; tavalist
temperatuuri kasutatakse ainult siis, kui näiv temperatuur puudub.

### Hinnapiirid

- **Alati sees selle efektiivhinnaga või alla** võib päevast tööaega suurendada, kui terve
  minimaalne tööperiood on piisavalt odav.
- **Alati väljas selle efektiivhinnaga või üle** välistab kallid perioodid, kuid päevane
  miinimum jääb ohutusnõudeks ja võib selle piiri ületada.
- Kui mõlemad on sees, peab „alati sees“ väärtus olema väiksem kui „alati väljas“ väärtus.

## Ohutus ja väljundi käitumine

- **Varirežiim** arvutab ja avaldab plaanid, kuid ei saada seadmetele käske.
- Integratsioon kasutab selgeid `homeassistant.turn_on` ja `homeassistant.turn_off`
  kutseid, mitte kunagi `toggle`.
- **Pööratud väljund** tähendab, et planeeritud tööajal saadetakse seadmele `turn_off`.
- Automaatjuhtimise lülitiga saab ühe seadme käsud välja lülitada.
- Andmete puudumisel saab valida, kas seade lülitatakse sisse, välja või jääb praegusesse
  olekusse.
- Integratsiooni mahalaadimine ei muuda seadme füüsilist olekut.
- Tegelikku tööaega loetakse esmalt võimsussensorist, siis tagasiside olemist ja lõpuks
  sihtolemist.

Enne varirežiimi väljalülitamist:

1. Jälgi vähemalt kahte täispäeva, sealhulgas homsete hindade avaldamist.
2. Võrdle plaani seadme tegeliku tagasiside või võimsuse ajalooga.
3. Kontrolli tariifide ühikuid: kõik hinnad ja tasud on ühikus `EUR/MWh`.
4. Testi pööratud väljundit ja käsijuhtimist mittekriitilise seadmega.
5. Veendu, et valitud käitumine andmevea korral on ohutu ka Home Assistanti või
   andmepakkuja katkestuse ajal.

## Olemid

Iga juhitav seade loob järgmised olemid:

| Platvorm | Otstarve |
| --- | --- |
| `binary_sensor` | Kas praegune intervall on plaani järgi aktiivne |
| `switch` | Seadme automaatjuhtimise lubamine või keelamine |
| `select` | Automaatne, Sund-ON või Sund-OFF käsijuhtimine |
| `datetime` | Valikuline käsijuhtimise lõpuaeg |
| `number` | Baas-, miinimum- ja maksimumtunnid ning küttekõvera seaded |
| `sensor` | Planeeritud, tegelikud ja puuduvad tunnid, järgmine olekumuutus, juhtimise põhjus |

Integratsioon salvestab tööaja loendurid ja käsijuhtimise Home Assistanti salvestusse ning
taastab need pärast taaskäivitust.

## Lovelace'i kaardid

Integratsioon serveerib kaartide JavaScripti aadressil:

```text
/smart_energy_scheduler/smart-energy-scheduler-card.js
```

Lisa see URL menüüs **Settings → Dashboards → Resources** tüübiga **JavaScript module** ja
lisa seejärel üks või mitu **Manual** kaarti. Kaartide tekstid on praegu eesti keeles.

### Kõigi seadmete plaan

```yaml
type: custom:smart-energy-scheduler-card
title: Energia planeerimine
hours: 48
```

Kaart näitab börsihindu, PV-toodangut, iga seadme plaani, varirežiimi või aktiivse juhtimise
olekut ning kahetunnise ON/OFF käsijuhtimise nuppe.

### Hinna ja töö graafik

```yaml
type: custom:smart-energy-price-plan-card
title: Hind ja soojuspumba plaan
target_entity: switch.heat_pump
hours: 48
```

Graafik ühendab varasema tegeliku töö, tulevased 15/60-minutilised plaanilõigud, ostuhinna,
seadme efektiivhinna ja PV-prognoosi.

### Muudetav küttekõver

```yaml
type: custom:smart-energy-heating-curve-card
title: Soojuspumba küttekõver
target_entity: switch.heat_pump
min_temperature: -25
max_temperature: 25
```

Seadmepõhistel kaartidel saab seadme valida võtmega `device_id`, `device` (seadistatud nimi)
või `target_entity`. Kui ühtegi pole antud, kasutatakse esimest seadet.

## Teenused

| Teenus | Kirjeldus |
| --- | --- |
| `smart_energy_scheduler.recalculate` | Loe sisendid, koosta plaan uuesti ja rakenda praegune intervall |
| `smart_energy_scheduler.set_override` | Sea seade automaatsele, Sund-ON või Sund-OFF režiimile |
| `smart_energy_scheduler.update_device_settings` | Muuda küttekõvera, planeerimise sammu ja hinnapiiride seadeid |

Käsijuhtimise näide:

```yaml
action: smart_energy_scheduler.set_override
data:
  device_id: 01EXAMPLEDEVICEID
  mode: "on"
  until: "2026-01-15 14:00:00"
```

Planeerija sisemine seadme ID on näha kaardi tehtud teenusekutsetes ja WebSocketi vastuses
`smart_energy_scheduler/get_plan`. Enamasti on lihtsam kasutada loodud käsijuhtimise
valikut kui teenust otse.

## Veaotsing

### Plaan pole saadaval

- Kontrolli, et `nordpool.hourly` on olemas menüüs **Settings → Tools → Actions**.
- Käivita `smart_energy_scheduler.recalculate` ja vaata integratsiooni logi.
- Poolik järgmine päev on normaalne, tänaste hindade puudumine ei ole.
- Vaata seadme **Juhtimise põhjus** sensorit ja kaartidel näidatud hoiatusi.

### Forecast.Solar on paigaldatud, aga PV on null

- Ava energiapaneeli seaded.
- Muuda päikesetoodangu allikat.
- Vali päikeseprognoosi pakkujate alt iga Forecast.Solari kirje.
- Arvuta plaan uuesti.

### Ilmapõhine juhtimine ei mõju

- Vali ühisseadetes ilmaolem.
- Kontrolli, et olem pakub tunnipõhist prognoosi.
- Lülita seadme sektsioonis **Ilmapõhine juhtimine** ilma arvestamine sisse.
- Vaata Lovelace'i kaardil varuplaani hoiatusi.

### Lovelace'i kaart ei uuene

- Kontrolli, et ressursi URL on lisatud tüübiga **JavaScript module**.
- Värskenda pärast integratsiooni uuendamist brauserit puhvrit tühjendades.
- Kontrolli, et integratsioon on laaditud ja ressursi URL tagastab JavaScripti.

## Uuendamine

HACS-i kaudu paigaldatud integratsiooni uuenda HACS-ist ja taaskäivita Home Assistant.
Käsitsi paigalduse korral asenda kogu integratsiooni kaust ja taaskäivita Home Assistant.
Ära kopeeri ainult üksikuid Pythoni faile, sest tõlked ja kaardid võivad koos muutuda.

## Arendus

Loo virtuaalkeskkond ja paigalda testide sõltuvused:

```bash
python -m venv .venv
.venv/bin/pip install -e '.[test]'
```

Käivita kontrollid:

```bash
.venv/bin/ruff check .
.venv/bin/pytest
```

GitHub Actions käivitab lisaks Home Assistanti `hassfest` ja HACS-i valideerimise.
Muudatused peavad säilitama salvestatud seadistuse ühilduvuse või sisaldama selget
migratsiooni.

## Projekti seis

Projekt on aktiivses arenduses. Käsitle seda eelversiooni automaatikatarkvarana ja kontrolli
iga plaani varirežiimis enne, kui lubad sel seadmeid juhtida. Vearaportid ja kitsalt
piiritletud muudatusettepanekud on GitHubi kaudu oodatud.

## Litsents

Avaldatud [MIT litsentsi](LICENSE) alusel.
