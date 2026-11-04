// Minimal shim: re-exports the AOSP libutils symbol `utf8_length` that
// Samsung's libsec-ims (Android 11) needs but Android 14 no longer exports.
// Faithful reimplementation of system/core/libutils Unicode.cpp utf8_length:
//   extern "C" ssize_t utf8_length(const char* src)
//   -> number of bytes of a valid (modified-)UTF-8 string, or -1 if malformed.
#include <sys/types.h>
#include <stdint.h>
#include <stddef.h>

namespace { constexpr uint32_t kUnicodeMaxCodepoint = 0x10FFFF; }

extern "C" ssize_t utf8_length(const char* src) {
    if (src == nullptr) return -1;
    const char* cur = src;
    ssize_t ret = 0;
    while (*cur != '\0') {
        const char first_char = *cur++;
        if ((first_char & 0x80) == 0) {            // ASCII
            ret += 1;
            continue;
        }
        if ((first_char & 0x40) == 0) {            // 10xxxxxx is not a valid lead byte
            return -1;
        }
        int32_t mask, to_ignore_mask;
        int num_to_read = 0;
        uint32_t utf32 = 0;
        for (num_to_read = 1, mask = 0x40, to_ignore_mask = 0xFFFFFF80;
             num_to_read < 5 && (first_char & mask);
             num_to_read++, to_ignore_mask |= mask, mask >>= 1) {
            if ((*cur & 0xC0) != 0x80) {           // continuation must be 10xxxxxx
                return -1;
            }
            utf32 = (utf32 << 6) + (*cur++ & 0x3F);
        }
        if (num_to_read == 5) {                    // sequences > 4 bytes invalid
            return -1;
        }
        to_ignore_mask |= mask;
        utf32 |= ((~to_ignore_mask) & first_char) << (6 * (num_to_read - 1));
        if (utf32 > kUnicodeMaxCodepoint) {
            return -1;
        }
        ret += num_to_read;
    }
    return ret;
}

