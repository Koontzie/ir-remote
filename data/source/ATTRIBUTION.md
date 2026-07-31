# IR data attribution

The two .ir files in this directory are not original work. They are the universal
IR library assets shipped with the Flipper Zero Unleashed firmware, taken from
applications/main/infrared/resources/infrared/assets/ in
https://github.com/DarkFlippers/unleashed-firmware, which is distributed under
GPL-3.0. Their file headers date them 2024-10-05; they were fetched for this
project on 2026-07-19.

tv.ir is the universal TV list (613 entries, 295 power codes).
projectors.ir is the universal projector list (302 entries, 138 power codes).

Those assets in turn build on the official Flipper Zero firmware,
https://github.com/flipperdevices/flipperzero-firmware, also GPL-3.0, and on
remote codes contributed by the community to Flipper-IRDB,
https://github.com/Lucaslhm/Flipper-IRDB, released under CC0-1.0.

data/tv.json and data/projectors.json are machine conversions of these files
produced by tools/flipper_ir_convert.py, which bit-reverses Flipper's LSB-first
bytes into the MSB-first form IRremoteESP8266 expects. They are derived works and
carry the same terms as their sources.

Because the upstream assets are GPL-3.0, anything that redistributes them needs to
be GPL-3.0 compatible. This repository does not yet carry a LICENSE file; GPL-3.0
is the straightforward choice. Regenerating the code library directly from
Flipper-IRDB, which is CC0-1.0, would remove that constraint.
