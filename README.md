# ir-remote

A small 3–5 button BLE-programmable universal remote. An ESP32-S3 fires IR codes at TVs, projectors, and soundbars; a self-contained Web Bluetooth page programs what each physical button does. Codes come from public IR databases, so no original remote is needed.

## How it works

```
[Web Bluetooth app] ──BLE GATT──> [ESP32-S3 firmware] ──> [IR LED via NPN] ──> device
[physical buttons] ──GPIO──────────────┘        config persisted in NVS
```

Five slots are stored in flash (NVS) and survive a power cycle. Protocols supported today: NEC, SAMSUNG, and SONY.

## Repo layout

`firmware/remote_ble/` holds the main sketch (NimBLE-Arduino + IRremoteESP8266); `firmware/phase1_ir_test/` is the minimal bring-up sketch. `app/index.html` is the whole web app, no build step. `data/` contains the converted code library plus the original Flipper `.ir` sources, and `tools/flipper_ir_convert.py` is the converter that bit-reverses Flipper's LSB-first bytes into IRremoteESP8266-ready values. `hardware/` has the KiCad project, wiring notes, and PCB design docs. `docs/DESIGN-code-library.md` explains the code library and identify-sweep design.

## Pin map (ESP32-S3)

| Signal | GPIO |
| --- | --- |
| IR LED (via NPN) | 4 |
| Button 1 | 5 |
| Button 2 | 2 |
| Button 3 | 7 |

Buttons wire GPIO → button → GND with `INPUT_PULLUP`. Avoid 0/3/45/46 (strapping), 19/20 (USB), and 26–37 (flash/PSRAM). Note that GPIO2 is a strapping pin on the classic ESP32 but not on the S3, so most "avoid these pins" lists online don't apply here.

## Running the app

Serve `app/` over localhost and open it in desktop Chrome, or use Bluefy on iOS. Web Bluetooth requires a secure context; `localhost` qualifies. Safari does not support Web Bluetooth.

```
cd app && python3 -m http.server 8000
```

## BLE interface

The device advertises as `IR-Remote` with one service and three characteristics: `config` (write) takes `{"slot":1,"proto":"SAMSUNG","code":"0xE0E040BF","bits":32}`, `trigger` (write) takes `{"slot":1}`, and `status` notifies `saved:N`, `sent:N`, or `err:...`.

The GATT server is currently unauthenticated: anyone in Bluetooth range can write config or trigger a slot. Fine for bench use; NimBLE bonding would close it.

## Credits and licensing

IR library data in `data/source/` comes from the Flipper Zero Unleashed firmware universal remote assets ([DarkFlippers/unleashed-firmware](https://github.com/DarkFlippers/unleashed-firmware), GPL-3.0), which build on the official Flipper Zero firmware assets (GPL-3.0) and on community submissions to [Flipper-IRDB](https://github.com/Lucaslhm/Flipper-IRDB) (CC0-1.0). See [data/source/ATTRIBUTION.md](data/source/ATTRIBUTION.md) for the full breakdown. Firmware built with IRremoteESP8266 and NimBLE-Arduino.

## Support

If you found this useful, you can buy me a coffee: [ko-fi.com/tylerxkoontz](https://ko-fi.com/tylerxkoontz)
