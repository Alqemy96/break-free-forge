// SPDX-License-Identifier: AGPL-3.0-or-later
// Break Free Forge - docs/templates/borderlands4_ps5.hexpat
//
// Borderlands 4 (PS5) save file - LAYOUT ONLY. No key. No save bytes.
//
//   on disk   C = AES-256-ECB_k( P )                       len(C) % 16 == 0
//   plaintext P = zlib_stream || u32le(uncompressed_len) || pad
//   pad       = PKCS7, 1..15 bytes, ABSENT (0 bytes) when the payload
//               (zlib_stream || trailer) is already a multiple of 16
//   zlib_stream inflates to UTF-8 YAML (~26 KB), no integrity field inside.
//
// ImHex cannot decrypt AES-ECB inline, so this template has three views:
//   1 ciphertext : the .sav as stored   -> 16-byte block grid only
//   2 container  : the DECRYPTED bytes P -> zlib / trailer / padding   (main use)
//   3 yaml       : the INFLATED text     -> top-level YAML sections
// The view is auto-detected. Override with the `view` input variable
// (Pattern Editor > Settings): 0 = auto, 1, 2, 3.
//
// How a key is recovered from YOUR OWN console's memory dump (the method,
// never the key): docs/runbooks/ORACLE_COOKBOOK.md
// Reference implementation: src/bl4forge/modules/save/_aes.py, _container.py
//
// Provenance: [V] = stated by the repo CONTEXT / working code,
//             [U] = unverified (see borderlands4_ps5.md "Known unknowns").
// Pattern-language features (`in` vars, global-scope `if`, while-arrays,
// std::assert_warn) are UNVERIFIED against a specific ImHex release.

#pragma author "Break Free Forge contributors"
#pragma description "Borderlands 4 (PS5) save: ciphertext grid, decrypted container, YAML sections"
#pragma endian little
#pragma pattern_limit 200000

import std.mem;
import std.core;
import std.io;

// ---------------------------------------------------------------- options --

u8 view in;   // 0 = auto-detect, 1 = ciphertext, 2 = container, 3 = yaml

// ---------------------------------------------------------------- helpers --

fn byte_at(u128 addr) {
    return std::mem::read_unsigned(addr, 1);
};

// RFC 1950 header sanity: CM = 8 (deflate), CINFO <= 7, no preset dict,
// (CMF*256 + FLG) % 31 == 0.
fn zlib_header_ok(u128 addr) {
    u8 cmf = byte_at(addr);
    u8 flg = byte_at(addr + 1);
    if ((cmf & 0x0F) != 8) return false;
    if ((cmf >> 4) > 7) return false;
    if ((flg & 0x20) != 0) return false;
    return ((u16(cmf) * 256 + flg) % 31) == 0;
};

// Padding length of the decrypted plaintext P.
// The payload ends with u32le(uncompressed_len). For len < 16 MiB its top
// byte is 0x00, so a final 0x00 means "no padding" (payload was aligned).
// Otherwise expect a PKCS7 run of n bytes of value n, n in 1..15.
fn padding_len() {
    u128 n = std::mem::size();
    u8 last = byte_at(n - 1);
    if (last == 0x00) return 0;
    if (last > 15) return 0;                  // malformed; asserts below report it
    u8 i = 0;
    while (i < last) {
        if (byte_at(n - 1 - i) != last) return 0;
        i = i + 1;
    }
    return last;
};

fn is_text(u128 count) {
    u128 n = std::mem::size();
    if (count > n) count = n;
    u128 i = 0;
    while (i < count) {
        u8 c = byte_at(i);
        if (c < 0x09) return false;
        if (c > 0x0D && c < 0x20) return false;
        if (c == 0x7F) return false;
        i = i + 1;
    }
    return true;
};

fn detect_view() {
    if (view != 0) return view;
    u128 n = std::mem::size();
    if (n >= 16 && n % 16 == 0 && zlib_header_ok(0)) return 2;
    if (is_text(256)) return 3;
    return 1;
};

// ------------------------------------------------- view 1: ciphertext (C) --

struct AesBlock {
    u8 bytes[16];
} [[static, color("707070"),
    comment("One AES-256-ECB block. ECB: equal plaintext blocks -> equal ciphertext blocks. [V]")]];

struct Bl4Ps5Ciphertext {
    std::assert(std::mem::size() % 16 == 0,
        "Ciphertext length is not a multiple of 16: not an AES-ECB save, or truncated.");
    AesBlock blocks[std::mem::size() / 16];
} [[comment("Encrypted save as stored. Decrypt offline with your own key, then re-open the plaintext (view 2).")]];

// -------------------------------------------------- view 2: container (P) --

enum ZlibLevel : u8 {
    Fastest = 0,
    Fast    = 1,
    Default = 2,
    Max     = 3
};

bitfield ZlibFlg {
    fcheck : 5 [[comment("Makes (CMF*256+FLG) % 31 == 0")]];
    fdict  : 1 [[comment("Preset dictionary; must be 0")]];
    ZlibLevel flevel : 2 [[comment("Compressor level hint only; does not affect decoding. Value the game uses: [U]")]];
};

struct ZlibHeader {
    u8 cmf [[comment("CM=8 deflate, CINFO=7 (32 KiB window) -> usually 0x78. [V: zlib stream per CONTEXT; exact byte U]")]];
    ZlibFlg flg;
} [[static, color("4FA3FF")]];

struct Bl4Ps5Container {
    u128 total   = std::mem::size();
    u8   pad     = padding_len();
    u128 payload = total - pad;

    std::assert(total % 16 == 0,
        "Plaintext length must be a multiple of 16 (it came out of AES-ECB).");
    std::assert(payload >= 2 + 4 + 4,
        "Too short for zlib header + Adler-32 + length trailer.");
    std::assert(zlib_header_ok(0),
        "No valid zlib header at offset 0: wrong key, wrong file, or this is still ciphertext.");
    std::assert_warn(byte_at(total - 1) == 0x00 || pad != 0,
        "Last byte is neither 0x00 (unpadded) nor a 1..15 PKCS7 run: padding rule violated.");

    ZlibHeader zlib_header;

    u8 deflate_data[payload - 2 - 4 - 4]
        [[color("2E7D32"),
          comment("Raw DEFLATE blocks (RFC 1951). Inflates to the UTF-8 YAML body. ImHex does not inflate it here. [V]")]];

    be u32 adler32
        [[color("F9A825"), format("std::string::to_string"),
          comment("Adler-32 of the inflated YAML, big-endian per RFC 1950. End of the zlib stream. [V: part of zlib stream]")]];

    le u32 uncompressed_length
        [[color("EF6C00"),
          comment("Inflated YAML size in bytes, little-endian. Must equal len(inflate(zlib_stream)): this plus a complete zlib stream is the decrypt validator. [V]")]];

    if (pad > 0) {
        u8 pkcs7_padding[pad]
            [[color("9E9E9E"),
              comment("PKCS7: n bytes of value n (1..15). Absent when the payload is block-aligned. [V]")]];
    }

    std::assert_warn(uncompressed_length > 0 && uncompressed_length < 0x01000000,
        "Unexpected uncompressed length (the YAML is normally about 26 KB). [U bound]");
} [[comment("Decrypted BL4 PS5 save: zlib_stream || u32le(len) || PKCS7 pad (0..15).")]];

// ------------------------------------------------------ view 3: YAML text --

// A top-level line starts at column 0 with something other than
// whitespace, '-', '#', or a line break.
fn is_top_level_start(u128 addr) {
    if (addr >= std::mem::size()) return false;
    if (addr != 0 && byte_at(addr - 1) != 0x0A) return false;
    u8 c = byte_at(addr);
    return c != 0x20 && c != 0x09 && c != 0x2D && c != 0x23 && c != 0x0A && c != 0x0D;
};

fn known_key(str k) {
    return k == "state"
        || k == "onlinecharacterprefs"
        || k == "pips"
        || k == "globals"
        || k == "stats"
        || k == "activities"
        || k == "missions"
        || k == "save_game_header"
        || k == "progression"
        || k == "timed_facts"
        || k == "domains";
};

fn fmt_section(ref auto s) {
    str k = std::format("{}", s.key);
    if (known_key(k)) return k;
    return k + "  (UNKNOWN top-level key: document it)";
};

struct YamlSection {
    char key[while(byte_at($) != 0x3A && byte_at($) != 0x0A && $ < std::mem::size())]
        [[comment("Top-level key name (unquoted). Order in file: [U]")]];
    char colon [[comment("':' separator")]];
    std::assert_warn(colon == ':', "Top-level line without ':' - not a mapping key.");
    char body[while($ < std::mem::size() && !is_top_level_start($))]
        [[comment("Indented YAML under this key, up to the next column-0 key. Edit semantically, not by byte offset: the game re-serializes on every load.")]];
} [[format("fmt_section"), color("7E57C2")]];

struct Bl4Ps5Yaml {
    char preamble[while($ < std::mem::size() && !is_top_level_start($))]
        [[comment("Anything before the first key ('---', comments). Presence: [U]")]];
    YamlSection sections[while($ < std::mem::size())];
} [[comment("Inflated save body: UTF-8 YAML. Top-level keys seen in the repo: state, stats, progression, domains. Also listed, UNVERIFIED: onlinecharacterprefs, pips, globals, activities, missions, save_game_header, timed_facts. No integrity field inside.")]];

// ------------------------------------------------------------- placement --

u8 g_view = detect_view();

if (g_view == 1) {
    Bl4Ps5Ciphertext ciphertext @ 0x00;
} else if (g_view == 2) {
    Bl4Ps5Container container @ 0x00;
} else {
    Bl4Ps5Yaml yaml @ 0x00;
}
