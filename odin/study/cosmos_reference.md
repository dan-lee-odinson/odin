Written by Muse Spark from the OpenC3 COSMOS v7.2.1 documentation, and modified from it.
Copyright © 2026 OpenC3, Inc.
Used under the OpenC3 Builder’s License, a copy of which is in this folder.

# COSMOS Operations Reference — Commands, Telemetry, Units, States, Limits and Alarms

This reference is for an operator that sends commands and reads telemetry through COSMOS. Use target, packet, and item names exactly as defined. Names never contain double underscore `__`, `[[` or `]]`, whitespace, and never end with underscore. Use upper case with underscores, for example `INST COLLECT`, `HEALTH_STATUS TEMP1`.

## 1. How to address a command or telemetry point

Commands:

`TARGET COMMAND with PARAM1 value1, PARAM2 value2`

Unspecified parameters use their defined default. If a parameter is marked `REQUIRED`, a script must supply it. Command Sender fills defaults automatically.

Telemetry:

`TARGET PACKET ITEM`

Example: `INST HEALTH_STATUS TEMP1`

Special packet name `LATEST` means most recent value across all packets that contain the item:

`INST LATEST TEMP1`

Use `LATEST` only for single items, not for whole-packet reads.

Every telemetry packet also has automatic items:

- `RECEIVED_TIMESECONDS`, `RECEIVED_TIMEFORMATTED` — when COSMOS received it
- `RECEIVED_COUNT` — receive counter
- `PACKET_TIMESECONDS`, `PACKET_TIMEFORMATTED` — mission time, if defined; otherwise same as received time
- `PACKET_TIME` — optional derived item defined with a time conversion to set true packet time for stored or delayed data

Formatted time is `YYYY/MM/DD HH:MM:SS.sss`. Seconds time is Unix seconds.

## 2. Command definitions

Defined in target `cmd_tlm` files, processed alphabetically.

`COMMAND TargetName CommandName BIG_ENDIAN|LITTLE_ENDIAN "description"`

Modifiers on `COMMAND`:

- `PARAMETER name bit_offset bit_size type ...` — fixed position. Bit offset 0 is most significant bit of first byte. Negative offset means from end of packet.
- `APPEND_PARAMETER name bit_size type ...` — appended after previous item. Preferred for normal use.
- `ID_PARAMETER / APPEND_ID_PARAMETER` — same as above but also identifies the packet. A command should have one or more ID parameters with fixed ID values. Packets with no ID are catch-all and match anything. Use `CATCHALL` to mark an intentional catch-all and suppress the warning. Use `VIRTUAL` for a structure definition that never participates in identification.
- `ARRAY_PARAMETER name bit_offset item_bit_size item_type array_bit_size "description"` and `APPEND_ARRAY_PARAMETER` — array field.
- `STRUCTURE / APPEND_STRUCTURE name bit_offset|bit_size CMD|TLM target packet` — flatten a virtual structure packet into this packet.
- `SELECT_COMMAND Target Command` + `SELECT_PARAMETER name` — edit an existing definition in a later file.
- `DELETE_PARAMETER name` — remove a parameter definition. Leaves a hole unless redefined.
- `HAZARDOUS "why hazardous"` — command always asks for confirmation.
- `DISABLED` — hidden and cannot be sent. Sending raises an error. Can be enabled/disabled at runtime by API.
- `HIDDEN` — hidden from Command Sender and completion, but still sendable by script.
- `DISABLE_MESSAGES` — do not print `cmd(...)` server message. Still logged to binary log.
- `META name values...` — custom metadata. Ignore unless your tooling uses it.
- `ACCESSOR name args...` — how raw bytes are read/written. Default is binary. For open-source use: Binary, CBOR, Form, HTML, HTTP, JSON, Template, XML. See absent list for Enterprise accessors.
- `TEMPLATE "string"`, `TEMPLATE_BASE64 base64`, `TEMPLATE_FILE path` — initial buffer for JSON/XML/template protocols before defaults are filled.
- `RESPONSE target packet`, `ERROR_RESPONSE target packet`, `RELATED_ITEM target packet item`, `SCREEN target screen` — expected response and operator hints. Used with command-response protocols.
- `VALIDATOR filename args...` — pre-check and post-check class for command success. `VALIDATOR` failures are reported in command history with description.
- `OVERFLOW ERROR|ERROR_ALLOW_HEX|TRUNCATE|SATURATE` on a parameter — what to do if a written value overflows INT/UINT size. Default is `ERROR`.
- `SUBPACKET`, `SUBPACKETIZER` — subpacket handling. `SUBPACKET` packets are excluded from interface-level identification and are broken out during decommutation.
- `RESTRICTED` — defined in files, but approval workflow is ABSENT in this build. See Section 10. Treat as a label only; no extra approval will be requested.

## 3. Command parameters in detail

Numeric types `INT UINT FLOAT DERIVED`:

`PARAMETER name offset size INT|UINT|FLOAT min max default "description" [endianness]`

String types `STRING BLOCK`:

`PARAMETER name offset size STRING|BLOCK default "description"`

`APPEND_` form omits offset.

Rules:

- `min max` can be numbers or `MIN MAX` for type extremes.
- `default` must always be given.
- `size 0` means fills to end of packet, or variable fill with negative size as offset from end. Only one variable-size item per packet.
- `offset 0 size 0 type DERIVED` means derived parameter with no bits in the packet. Must have a write conversion to compute it.
- Extra types `BOOL ARRAY OBJECT ANY` only with an accessor that supports them.
- `REQUIRED` — script must supply a value; default is not accepted.
- `MINIMUM_VALUE`, `MAXIMUM_VALUE`, `DEFAULT_VALUE` — override defined value when selecting/editing.
- `OVERLAP` — allow this item to overlap another without warning.
- `KEY key-string` — key for JSONPath/XPath accessors, for example `$.item1`.
- `VARIABLE_BIT_SIZE length_item [bits_per_count] [bit_offset]` — size defined by another length item.
- `OBFUSCATE` — hide value in UI, text logs, and raw file.
- `HIDDEN` on a parameter — hide from tools; do not supply it; usually filled by conversion.

Array example: array of ten 64-bit floats, total 640 bits.

Do not use brackets in names. `ARRAY [1,2,3]` syntax in commands refers to array values, not name brackets.

## 4. Telemetry definitions

`TELEMETRY TargetName PacketName BIG_ENDIAN|LITTLE_ENDIAN "description"`

Modifiers on `TELEMETRY`:

- `ITEM name bit_offset bit_size type "description"` — fixed position.
- `APPEND_ITEM name bit_size type "description"` — appended.
- `ID_ITEM / APPEND_ID_ITEM name offset|size type id_value "description"` — identification field. All ID values must match for packet to identify. Ideally all packets in a target use same offset/size/type for ID.
- `ARRAY_ITEM name offset item_bit_size item_type array_bit_size "description"` and `APPEND_ARRAY_ITEM` — array item.
- `STRUCTURE / APPEND_STRUCTURE` — same as commands.
- `SELECT_TELEMETRY Target Packet` + `SELECT_ITEM name` — edit existing definition.
- `DELETE_ITEM name` — remove item definition. Leaves hole unless redefined.
- `ALLOW_SHORT` — accept packets shorter than defined without warning; missing bytes filled with zero.
- `HIDDEN` — hidden from Packet Viewer, grapher, handbooks, and completion, but still received and usable in screens by explicit reference.
- `IGNORE_OVERLAP` — ignore all overlap warnings in this packet.
- `CATCHALL`, `VIRTUAL`, `SUBPACKET`, `SUBPACKETIZER`, `ACCESSOR`, `TEMPLATE`, `TEMPLATE_FILE`, `TEMPLATE_BASE64`, `META`, `PROCESSOR` — same meaning as commands.
- `LIMITS_GROUP name` + `LIMITS_GROUP_ITEM target packet item` — named group for bulk enable/disable. Usually in `limits_groups.txt`.

Derived items:

`ITEM name 0 0 DERIVED "description"` plus a `READ_CONVERSION`.

Derived items have no bits. Place at end of packet. They always sort last in API listings regardless of file order. They must have a conversion to produce a value.

Variable-size items: `bit_size 0` collects all undefined bytes. Typically memory dumps. Only one per packet.

## 5. Data types

Binary types:

- `INT` — signed integer
- `UINT` — unsigned integer
- `FLOAT` — floating point, 32 or 64 bit
- `STRING` — text; reading stops at null byte for display, but nulls are legal on write
- `BLOCK` — binary; use for non-ASCII; display as hex with `formatted()`
- `DERIVED` — no bits, computed

Accessor types: `BOOL ARRAY OBJECT ANY TIME` — only valid when the packet `ACCESSOR` supports them.

Endianness: packet default `BIG_ENDIAN` or `LITTLE_ENDIAN`. Individual items can override. Little-endian bitfields must give offset in big-endian space at the most significant bit. Do not use `APPEND` for little-endian bitfields; use explicit offsets and verify with View Raw.

## 6. Units and display formatting

On any command parameter, telemetry item, or table parameter:

`UNITS FullName Abbrev`

Example:

```
UNITS Celsius C
UNITS Seconds S
UNITS Kilometers KM
```

`UNITS` affects display only. Raw and converted numeric values are unchanged. Formatted value appends units.

`FORMAT_STRING "printf-format"`

Example: `FORMAT_STRING "0x%0X"` shows hex, `FORMAT_STRING "%0.3f"` shows 3 decimals.

For telemetry, three value types are available:

- `RAW` — bits as stored, after accessor, before conversion
- `CONVERTED` — after read conversion and states; default for operations
- `FORMATTED` — converted as string with format and units

If no conversion/format/units is defined, all three are effectively the same except string type.

When scripting, request type explicitly when needed: `tlm(..., type='RAW')`, `check(..., type='RAW')`, `wait(..., type='RAW')`. Packet subscriptions return `ITEM` for raw, `ITEM__C` for converted, `ITEM__F` for formatted, `ITEM__L` for limits state.

Tables also support `UNEDITABLE` — show but do not allow edit — and parameter-level `HIDDEN` to hide padding from Table Manager but still save it to binary.

## 7. States

`STATE name value [color|HAZARDOUS] [hazardous-description]`

For commands:

```
APPEND_PARAMETER ENABLE 8 UINT 0 1 0 "Enable"
  STATE DISABLE 0
  STATE ENABLE 1
```

For command strings:

```
STATE "ARM LASER" "ARM LASER" HAZARDOUS "eye hazard"
```

`HAZARDOUS` on a state prompts for confirmation only when that state value is used. `DISABLE_MESSAGES` as third field suppresses command logging for that state value.

For telemetry:

```
APPEND_ITEM MODE 8 UINT "Mode"
  STATE NORMAL 0 GREEN
  STATE DIAG 1 YELLOW
```

Telemetry state colors allowed: `GREEN YELLOW RED`. Special value `ANY` catches all other values:

`STATE ERROR ANY RED`

Use states for operator readability. Sending a command can use state name instead of number. Reading telemetry with states returns the state name as converted value; raw is still the number.

## 8. Conversions

Conversions transform values on write (commands) or read (telemetry).

- Commands: `WRITE_CONVERSION file.py params...`, `POLY_WRITE_CONVERSION c0 c1...`, `SEG_POLY_WRITE_CONVERSION ...`, `GENERIC_WRITE_CONVERSION_START ... GENERIC_WRITE_CONVERSION_END`
- Telemetry: `READ_CONVERSION file.py params...`, `POLY_READ_CONVERSION c0 c1...`, `SEG_POLY_READ_CONVERSION ...`, `GENERIC_READ_CONVERSION_START ... GENERIC_READ_CONVERSION_END`, plus `CONVERTED_DATA bit_size type [array_size]` for derived/generic types

Built-in conversions available in this build:

- `POLYNOMIAL_CONVERSION` / `POLY_READ|WRITE_CONVERSION` — `value = c0 + c1*x + c2*x^2 ...`
- `SEGMENTED_POLYNOMIAL_CONVERSION` / `SEG_POLY_READ|WRITE_CONVERSION` — different polynomial per lower-bound segment
- `GENERIC_CONVERSION` — inline code with `value` and `packet` available; last line is return value. Slower; prefer a file conversion for permanent use.
- `BIT_REVERSE_CONVERSION` — bit-reverse, read or write
- `IP_READ_CONVERSION` / `IP_WRITE_CONVERSION` — 32-bit packed int to/from `x.x.x.x` string
- `OBJECT_READ|WRITE_CONVERSION CMD|TLM target packet` — pack/unpack whole packet object
- `UNIX_TIME_CONVERSION seconds_item [micro_item]`, `UNIX_TIME_FORMATTED_CONVERSION`, `UNIX_TIME_SECONDS_CONVERSION` — build time object for `PACKET_TIME`
- `PACKET_TIME_FORMATTED|SECONDS_CONVERSION`, `RECEIVED_TIME_FORMATTED|SECONDS_CONVERSION`, `RECEIVED_COUNT_CONVERSION` — automatic internal conversions; do not set manually
- `PROCESSOR_CONVERSION processor_name value_name` — pull a processor result into a derived item

Custom conversions live in target `lib` and implement `call(value, packet, buffer)`. Write conversions may run twice (defaults then user values) and order is not guaranteed; use `packet.given_values` to read user inputs.

For telemetry derived items that change type, add `CONVERTED_DATA`. Example: 32-bit float result:

```
GENERIC_READ_CONVERSION_START
  value * 1.5
GENERIC_READ_CONVERSION_END
CONVERTED_DATA 32 FLOAT
```

Without `CONVERTED_DATA`, derived values store as strings in decommutated data.

Processors run on every packet receipt and publish multiple results:

`PROCESSOR name file.py params...`

Built-ins:

- `WATERMARK_PROCESSOR item [RAW|CONVERTED]` — publishes `HIGH_WATER`, `LOW_WATER`
- `STATISTICS_PROCESSOR item num_samples [RAW|CONVERTED]` — publishes `MIN MAX MEAN STDDEV`

Retrieve with a derived item + `PROCESSOR_CONVERSION`.

## 9. Limits, limit states, and alarms

Limits are only on telemetry items with numeric values or colored states.

Definition:

`LIMITS set persistence enabled red_low yellow_low yellow_high red_high [green_low green_high]`

Example:

```
LIMITS DEFAULT 3 ENABLED -80.0 -70.0 60.0 80.0 -20.0 20.0
LIMITS TVAC 3 ENABLED -80.0 -30.0 30.0 80.0
```

Fields:

- `set` — limits set name. `DEFAULT` is required and must be defined first before any other set like `TVAC`. Active set is system-wide; change via Limits Monitor or `set_limits_set`.
- `persistence` — consecutive samples outside current state required before changing state. Prevents flicker.
- `enabled` — `ENABLED` or `DISABLED` initial monitoring state. All `LIMITS` lines for one item should agree.
- `red_low yellow_low yellow_high red_high` — thresholds. Low violation is `<=`, high violation is `>=`.
- `green_low green_high` — optional operational band inside green. Values inside show as blue.

State-based limits: if an item has `STATE ... RED` or `YELLOW`, that state drives limits instead of numeric thresholds. Numeric `LIMITS` and state colors should not conflict.

Runtime limit states for numeric items:

- `RED_LOW` — at or below red low
- `YELLOW_LOW` — at or below yellow low but above red low
- `GREEN_LOW` — below green low but inside yellow/green; transitional toward blue
- `BLUE` — inside green_low to green_high operational band, when defined
- `GREEN_HIGH` — above green high but inside yellow/green
- `GREEN` — normal, inside yellow thresholds and outside blue if defined
- `YELLOW_HIGH` — at or above yellow high but below red high
- `RED_HIGH` — at or above red high
- `RED`, `YELLOW` — for state items with red/yellow states
- Stale or disabled items do not alarm.

Overall system state is `GREEN`, `YELLOW`, or `RED` — worst of all enabled, non-ignored items. Use ignored lists and limits groups to suppress known issues. Ignored state is shown as `(Some items ignored)`.

Alarming behavior:

- On change after persistence, COSMOS logs a limits event, colors displays, updates overall state, and fires `LIMITS_RESPONSE` if defined.
- `LIMITS_RESPONSE file.py options...` — custom code on every state change with old state available. Use for automatic safing. Keep actions idempotent.
- `ENABLED/DISABLED` can be toggled per item or per `LIMITS_GROUP` via `enable_limits`, `disable_limits`, `enable_limits_group`, `disable_limits_group`. Group membership is last-wins.
- `get_limits`, `set_limits`, `get_out_of_limits`, `get_overall_limits_state`, `get_limits_event` provide programmatic access.
- Limits Monitor shows current violators plus history. Packet-level ignore suppresses whole packet; item ignore suppresses one item; hide temporarily clears display but will re-show on next violation.

Stored telemetry handling per target (`STORED_LIMITS_MODE` in plugin):

- `PROCESS` (default) — stored packets alarm, log, fire responses, and update overall state like realtime.
- `LOG` — evaluate and log/publish state changes, but do not fire `LIMITS_RESPONSE` and do not update overall current state.
- `DISABLE` — skip limits entirely for stored packets; no events; no `__L` in decom.

Realtime packets always use `PROCESS` regardless of this setting. Stored packets never update the current value table, so they never affect Packet Viewer, Telemetry Viewer live values, or `LATEST` lookups, but they are still logged and available to Grapher/Extractor.

## 10. Absent in this build — Enterprise-only, do not use

The following are described in full COSMOS docs as Enterprise-only. In this open-source build they are ABSENT. Do not attempt to configure or rely on them. They will not work.

- Command Authority — ABSENT. No take/release of command authority, no exclusive command/script lock per target, no Scopes-tab enable. All defined users can send commands subject to normal hazardous/disabled checks.
- Critical Commanding and approvals — ABSENT. No `NORMAL/ALL/OFF` critical mode, no approver role, no approve/reject workflow for `HAZARDOUS`, `RESTRICTED`, or all manual commands. `HAZARDOUS` still prompts Are-You-Sure locally, but no second-user approval exists. `RESTRICTED` has no approval effect in this build. Calendar/Autonomic exemption from authority does not apply.
- GEMS Ascii accessor — ABSENT.
- Prometheus accessor — ABSENT.
- Protocol Buffer accessor (`ProtoAccessor`) and protobuf code generation — ABSENT.
- SNMP Interface — ABSENT.
- SNMP Trap Interface — ABSENT.
- gRPC Interface and `META GRPC_METHOD` commanding — ABSENT.
- InfluxDB Interface — ABSENT.
- GEMS Protocol — ABSENT.
- CCSDS CLTU Protocol with BCH — ABSENT.
- CCSDS TCTF Protocol — ABSENT.
- CCSDS TMTF Protocol — ABSENT.
- `CONTAINER` deployment directive for interfaces/microservices — ABSENT. Do not specify alternate containers.

If a definition references any absent accessor, interface, protocol, or approval, treat that definition as invalid for this build and replace with an open-source Binary, JSON, CBOR, Template, XML, Form, HTTP, Length, Fixed, Burst, Terminated, COBS, SLIP, Preidentified, CRC, Command-Response, or Ignore helper as appropriate.
