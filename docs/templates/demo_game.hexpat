// SPDX-License-Identifier: AGPL-3.0-or-later
// Break Free Forge - docs/templates/demo_game.hexpat
//
// *** FICTIONAL FORMAT. "Demo Game" does not exist. ***
// This file shows the quality bar expected from contributed templates:
// header comment, pragmas, enums/bitfields, a section table with
// placed sections, hard asserts, soft warnings, and a provenance tag
// ([V] verified / [U] unverified) on every non-obvious field.
//
//   +--------+------------------+---------------------+--------+
//   | Header | SectionEntry[n]  | section payloads... | Footer |
//   +--------+------------------+---------------------+--------+
//
// Checked against: n/a (fictional). Real templates name game version + date.

#pragma author "Break Free Forge contributors"
#pragma description "Demo Game save (FICTIONAL example template)"
#pragma endian little

import std.mem;
import std.core;
import std.string;

// ------------------------------------------------------------------ enums --

enum Platform : u8 {
    PC      = 0x00,
    Console = 0x01,
    Handheld = 0x02
};

enum SectionKind : u32 {
    Player    = 0x00000001,
    Inventory = 0x00000002,
    World     = 0x00000003,
    Settings  = 0x00000010
};

enum Compression : u8 {
    None = 0,
    Zlib = 1
};

bitfield HeaderFlags {
    has_footer      : 1 [[comment("Footer present at EOF. [V]")]];
    big_sections    : 1 [[comment("Section sizes are u32 instead of u16. Always 1 in observed files. [U]")]];
    autosave        : 1 [[comment("Written by autosave, not a manual save. [V]")]];
    reserved        : 5 [[comment("Always 0 so far. [U]")]];
};

// ----------------------------------------------------------------- header --

struct Header {
    char magic[4] [[comment("ASCII 'DMSV'. [V]")]];
    std::assert(magic == "DMSV", "Not a Demo Game save (bad magic).");

    u16 format_version [[comment("Observed: 3. Bump means re-check every field. [V]")]];
    std::assert_warn(format_version == 3, "Unseen format_version: template may be out of date.");

    Platform platform;
    HeaderFlags flags;
    u32 section_count [[comment("Entries in the section table. [V]")]];
    std::assert(section_count > 0 && section_count < 64, "Implausible section_count.");

    u64 saved_at [[comment("Unix seconds, UTC. [U: could be local time]")]];
} [[static, color("4FA3FF")]];

// --------------------------------------------------------------- sections --

struct PlayerSection {
    u16 name_len [[comment("UTF-8 byte length, no terminator. [V]")]];
    char name[name_len];
    u32 level    [[comment("1..100 in practice. [V]")]];
    float health [[comment("IEEE-754 single. [V]")]];
    u32 currency [[comment("[U: may be signed]")]];
} [[color("2E7D32")]];

struct InventoryItem {
    u32 item_id  [[comment("Opaque id into game data. Do NOT add a name table here (copyrighted data). [V]")]];
    u16 quantity;
    u16 slot     [[comment("0xFFFF = not equipped. [U]")]];
} [[static]];

struct InventorySection {
    u32 count;
    InventoryItem items[count];
} [[color("F9A825")]];

struct SectionEntry {
    SectionKind kind;
    u32 offset [[comment("Absolute file offset of the payload. [V]")]];
    u32 size   [[comment("Payload size in bytes (stored size if compressed). [V]")]];
    Compression compression;
    padding[3];
    u32 crc32  [[comment("CRC-32 (IEEE) of the stored payload. Not checked here. [V]")]];

    std::assert(offset + size <= std::mem::size(), "Section runs past end of file.");

    if (compression == Compression::None) {
        if (kind == SectionKind::Player)         PlayerSection    payload @ offset;
        else if (kind == SectionKind::Inventory) InventorySection payload @ offset;
        else u8 opaque_payload[size] @ offset [[color("9E9E9E"), comment("Not reversed yet. [U]")]];
    } else {
        u8 compressed_payload[size] @ offset
            [[comment("zlib stream. Inflate outside ImHex, then apply the section struct. [V]")]];
    }
} [[format("fmt_entry")]];

fn fmt_entry(ref SectionEntry e) {
    return std::format("{} @ 0x{:X} ({} bytes)", e.kind, e.offset, e.size);
};

// ----------------------------------------------------------------- footer --

struct Footer {
    char magic[4]   [[comment("ASCII 'DEND'. [V]")]];
    std::assert(magic == "DEND", "Bad footer magic.");
    u32 total_size  [[comment("Must equal file size. [V]")]];
    std::assert(total_size == std::mem::size(), "Footer total_size disagrees with file size.");
} [[static, color("EF6C00")]];

// --------------------------------------------------------------- file root --

struct DemoSave {
    Header header;
    SectionEntry sections[header.section_count];
    if (header.flags.has_footer) {
        Footer footer @ std::mem::size() - 8;
    }
} [[comment("Demo Game save (FICTIONAL).")]];

DemoSave save @ 0x00;
