# Phase 3's space weather: sources and terms

**Held out** with the phase-3 document beside it. Nothing here goes to Muse Code, ODIN or Muse Code's workspace.

Downloaded by Claude Code on 28 October 2026 on the Director's ruling of that morning (item 3): the averaged east and west sensor values for the >10, >30 and >60 MeV integral proton fluxes, and the geomagnetic Kp index for the same days. Both are replayed from the flare at each scenario's epoch, and labeled replayed (phase-3 document §2 and §6, sha256:ccbb09f269c3ee17b90ad38a5180f4c2857b5ee55dcb7905c01d192780ec9c37).

The days are 10 and 11 September 2017 (UTC). The flare is the X8.2 of 10 September at about 15:35 UT. The longest phase-3 run is a few hours, so two days cover every replay with room to spare.

## The files in `raw/`, as downloaded

| File | SHA-256 | What it is |
|---|---|---|
| `goes13_5min_2017-09-10_11.html` | `440d06d540c1bf4be2ae3b03209c5e1c15bf9dc2c4aea4daec6e2496cbccc020` | OMNIWeb Plus's listing page: 576 five-minute rows, 2017-09-10 00:00 to 2017-09-11 23:55 UT, no gaps and no fill values |
| `kp_gfz_2017-09-10_11.json` | `7e059bf552a5a2b50ccd8dbc7a52b6fe4043a7a315e19490abe9b9463b96b4c5` | GFZ's Kp web service's answer: 16 three-hour values, all of status `def` (definitive) |

They are kept byte for byte. The replay is made from them; they are never edited.

## GOES-13 integral proton fluxes

- **Source.** NASA Space Physics Data Facility, OMNIWeb Plus, "Integral proton fluxes from GOES13,14", https://omniweb.gsfc.nasa.gov/ftpbrowser/goes13_14_flux_5m.html. Its page says the values come from the east- and west-looking sensors of the Space Environment Monitor on GOES-13 (at 74° W), taken from NOAA at https://satdat.ngdc.noaa.gov/sem/goes/data/new_avg/, and that "Av" is the average of the E and W fluxes. GOES-13 covers 2011-01-01 to 2017-12-01.
- **Request.** POST to https://omniweb.gsfc.nasa.gov/cgi/nx1.cgi with `activity=retrieve`, `spacecraft=goes13_14_flux_5m`, `res=5min`, `start_date=20170910`, `end_date=20170911`, and `vars` 04, 05 and 06: `Prot flux_Av (>10 Mev)`, `(>30 Mev)` and `(>60 Mev)`.
- **Units.** The form labels the fluxes "1/cm**2-sec-ster-MeV/nuc". The values are integral fluxes above each energy, the quantity NOAA gives in particle flux units (cm⁻² s⁻¹ sr⁻¹). The README should give the unit with that note.
- **Terms.** OMNIWeb's citing page (https://omniweb.gsfc.nasa.gov/html/citing.html) asks that use of data other than the OMNI datasets be cited "inline in the body of text when first appropriate and/or in an Acknowledgement section". It names no license. The README acknowledges NASA SPDF's OMNIWeb Plus and NOAA's GOES-13 Space Environment Monitor, with the date of access.

## The Kp index

- **Source.** GFZ German Research Centre for Geosciences, Potsdam, the Kp index's producer. Web service https://kp.gfz.de/app/json/ (the old host kp.gfz-potsdam.de redirects there).
- **Request.** `start=2017-09-10T00:00:00Z`, `end=2017-09-11T23:59:59Z`, `index=Kp`, `status=def`.
- **Terms.** CC BY 4.0, as the service's answer states (`"meta": {"license": "CC BY 4.0", "source": "GFZ Potsdam"}`). The citation, from the dataset's DOI page: Matzka, J., Bronkalla, O., Tornow, K., Elger, K. and Stolle, C. (2021), Geomagnetic Kp index, V. 1.0, GFZ Data Services, https://doi.org/10.5880/Kp.0001.

## The event in these files

From the flare at 15:35 UT, the averaged >30 and >60 MeV fluxes pass 1 pfu at 16:25 UT (50 min), and >10 MeV passes 10 pfu, NOAA's S1 threshold, at 16:45 UT (70 min). At 17:35 UT (2 h) >10 MeV reads 185. The >60 MeV flux peaks at 150 at 22:20 UT on the 10th, >30 MeV at 423 at 01:00 UT on the 11th, and >10 MeV at 1298 at 11:40 UT on the 11th. Kp runs 0 to 3.3 over the two days.
