/*
 * PrismaRGB Direct Userspace AMD FCH PIIX4 SMBus Helper & Daemon
 *
 * Implements the exact Corsair Vengeance RGB DDR5 (CMH32GX5M2B6000Z30)
 * SMBus protocol on AMD FCH PIIX4 Port 0x0B00 (Addresses 0x19 & 0x1B),
 * bypassing the Gigabyte B650E AORUS ELITE X AX ICE ACPI (\GSA1.SMBI) lock.
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <sys/io.h>
#include <sys/stat.h>

#define PIIX4_SMB_BASE_PRIMARY   0x0B00

/* PIIX4 SMBus register offsets */
#define SMBHSTSTS  0x00
#define SMBHSLVSTS 0x01
#define SMBHSTCNT  0x02
#define SMBHSTCMD  0x03
#define SMBHSTADD  0x04
#define SMBHSTDAT0 0x05
#define SMBHSTDAT1 0x06
#define SMBBLKDAT  0x07

/* Control register bits */
#define PIIX4_BYTE_DATA  0x08
#define PIIX4_WORD_DATA  0x0C
#define PIIX4_BLOCK_DATA 0x14
#define PIIX4_START      0x40

/* Status register bits */
#define SMBHSTSTS_BUSY   0x01
#define SMBHSTSTS_INTR   0x02
#define SMBHSTSTS_DEVERR 0x04
#define SMBHSTSTS_BUSERR 0x08
#define SMBHSTSTS_FAILED 0x10

static uint8_t crc8_corsair(const uint8_t *data, size_t len) {
    uint8_t crc = 0x00;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int b = 0; b < 8; b++) {
            if (crc & 0x80) {
                crc = (uint8_t)((crc << 1) ^ 0x07);
            } else {
                crc = (uint8_t)(crc << 1);
            }
        }
    }
    return crc;
}

static int smbus_wait(uint16_t base) {
    int timeout = 0;
    uint8_t sts;
    usleep(150);
    while (((sts = inb(base + SMBHSTSTS)) & SMBHSTSTS_BUSY) && (timeout++ < 800)) {
        usleep(80);
    }
    if (timeout >= 800) {
        outb(sts, base + SMBHSTSTS);
        return -1;
    }
    if (sts & (SMBHSTSTS_FAILED | SMBHSTSTS_BUSERR | SMBHSTSTS_DEVERR)) {
        outb(sts, base + SMBHSTSTS);
        return -2;
    }
    if (sts & SMBHSTSTS_INTR) {
        outb(SMBHSTSTS_INTR, base + SMBHSTSTS);
    }
    return 0;
}

static void smbus_clear(uint16_t base) {
    uint8_t sts = inb(base + SMBHSTSTS);
    if (sts != 0x00) {
        outb(sts, base + SMBHSTSTS);
        usleep(80);
    }
}

static int smbus_read_byte_data(uint16_t base, uint8_t addr, uint8_t reg) {
    smbus_clear(base);
    outb(((addr & 0x7f) << 1) | 0x01, base + SMBHSTADD);
    outb(reg, base + SMBHSTCMD);
    outb(PIIX4_BYTE_DATA | PIIX4_START, base + SMBHSTCNT);
    if (smbus_wait(base) < 0) {
        return -1;
    }
    return (int)inb(base + SMBHSTDAT0);
}

static int smbus_write_byte_data(uint16_t base, uint8_t addr, uint8_t reg, uint8_t val) {
    smbus_clear(base);
    outb(((addr & 0x7f) << 1) | 0x00, base + SMBHSTADD);
    outb(reg, base + SMBHSTCMD);
    outb(val, base + SMBHSTDAT0);
    outb(PIIX4_BYTE_DATA | PIIX4_START, base + SMBHSTCNT);
    return smbus_wait(base);
}

static int smbus_write_word_data(uint16_t base, uint8_t addr, uint8_t reg, uint16_t val) {
    smbus_clear(base);
    outb(((addr & 0x7f) << 1) | 0x00, base + SMBHSTADD);
    outb(reg, base + SMBHSTCMD);
    outb((uint8_t)(val & 0xFF), base + SMBHSTDAT0);
    outb((uint8_t)((val >> 8) & 0xFF), base + SMBHSTDAT1);
    outb(PIIX4_WORD_DATA | PIIX4_START, base + SMBHSTCNT);
    return smbus_wait(base);
}

static int smbus_write_block_data(uint16_t base, uint8_t addr, uint8_t reg, const uint8_t *data, uint8_t len) {
    if (len > 32) len = 32;
    smbus_clear(base);
    outb(((addr & 0x7f) << 1) | 0x00, base + SMBHSTADD);
    outb(reg, base + SMBHSTCMD);
    outb(len, base + SMBHSTDAT0);
    (void)inb(base + SMBHSTCNT); /* Reset PIIX4 internal block buffer pointer to 0 */
    for (uint8_t i = 0; i < len; i++) {
        outb(data[i], base + SMBBLKDAT);
    }
    outb(PIIX4_BLOCK_DATA | PIIX4_START, base + SMBHSTCNT);
    return smbus_wait(base);
}

static void corsair_wait_ready(uint16_t base, uint8_t addr) {
    for (int i = 0; i < 10; i++) {
        int st = smbus_read_byte_data(base, addr, 0x30);
        if (st >= 0 && ((st & 0x08) == 0)) {
            return;
        }
        usleep(1000);
    }
}

static int g_initialized_19 = 0;
static int g_initialized_1b = 0;

static void corsair_init_custom_mode(uint16_t base, uint8_t addr) {
    /*
     * Send 20-byte SetEffect packet (mode 0x04 = Static/Per-LED Custom)
     * followed by CRC8 verify (reg 0x42) and Commit Effect (reg 0x82 = 0x01).
     */
    uint8_t eff[20];
    memset(eff, 0, sizeof(eff));
    eff[0] = 0x04; /* CORSAIR_DRAM_MODE_STATIC (per-LED buffer via 0x20/0x82=0x02) */
    eff[1] = 0x00; /* Speed */
    eff[2] = 0x00; /* Direction */
    eff[3] = 0x01; /* Custom colors enabled */
    eff[11] = 0xFF;
    eff[15] = 0xFF;
    eff[19] = 0xFF;

    smbus_write_byte_data(base, addr, 0x0B, 0x00);
    smbus_write_byte_data(base, addr, 0x21, 0x00);
    for (int i = 0; i < 20; i++) {
        smbus_write_byte_data(base, addr, 0x20, eff[i]);
    }
    uint8_t crc = crc8_corsair(eff, 20);
    int hw_crc = smbus_read_byte_data(base, addr, 0x42);
    if (hw_crc < 0 || (uint8_t)hw_crc == crc) {
        smbus_write_byte_data(base, addr, 0x82, 0x01);
        corsair_wait_ready(base, addr);
    }
}

/*
 * Exact CorsairDRAMController (Corsair Vengeance RGB DDR5 @ 0x19 / 0x1B) 10-LED update:
 * Supports both:
 *   1) Protocol v4/v5 Direct 32-byte frame (cmd 0x31 block write + 0x90/0xA0 word stream fallback)
 *   2) Byte-stream register 0x20 + CRC8 check (0x42) + Commit (0x82 = 0x02)
 */
static int write_corsair_ddr5_10leds(uint16_t base, uint8_t addr, const uint8_t rgb[30]) {
    if (addr == 0x19 && !g_initialized_19) {
        corsair_init_custom_mode(base, addr);
        g_initialized_19 = 1;
    } else if (addr == 0x1B && !g_initialized_1b) {
        corsair_init_custom_mode(base, addr);
        g_initialized_1b = 1;
    }
    /* 1. Build 32-byte Direct packet: [10, R0,G0,B0 .. R9,G9,B9, CRC8] */
    uint8_t pkt[32];
    pkt[0] = 10; /* 10 LEDs on Corsair Vengeance RGB DDR5 */
    memcpy(&pkt[1], rgb, 30);
    pkt[31] = crc8_corsair(pkt, 31);

    /* Try SMBus Block Write to 0x31 first */
    if (smbus_write_block_data(base, addr, 0x31, pkt, 32) < 0) {
        /* Word-data stream fallback (0x90 / 0xA0) from CorsairDRAMController::SetDirectColor */
        uint8_t prefix = 0x90;
        for (int i = 0; i < 32; i += 5) {
            uint16_t w1 = pkt[i];
            if (i + 1 < 32) w1 |= ((uint16_t)pkt[i + 1] << 8);
            if (i + 2 < 32) {
                uint8_t b2 = pkt[i + 2];
                uint8_t cmd1 = prefix | (b2 & 0x0F);
                uint8_t cmd2 = 0xA0 | ((b2 >> 4) & 0x0F);
                smbus_write_word_data(base, addr, cmd1, w1);
                uint16_t w2 = 0;
                if (i + 3 < 32) w2 = pkt[i + 3];
                if (i + 4 < 32) w2 |= ((uint16_t)pkt[i + 4] << 8);
                smbus_write_word_data(base, addr, cmd2, w2);
            } else {
                smbus_write_word_data(base, addr, prefix, w1);
            }
            prefix = 0xA0;
        }
    }

    /* 2. Also update the 0x20 byte-stream buffer & commit (0x82 = 0x02) for firmware v1-v3 compatibility */
    uint8_t buf40[40];
    for (int i = 0; i < 10; i++) {
        buf40[i * 4 + 0] = rgb[i * 3 + 0];
        buf40[i * 4 + 1] = rgb[i * 3 + 1];
        buf40[i * 4 + 2] = rgb[i * 3 + 2];
        buf40[i * 4 + 3] = 0xFF;
    }
    smbus_write_byte_data(base, addr, 0x0B, 0x00);
    smbus_write_byte_data(base, addr, 0x21, 0x00);
    for (int i = 0; i < 40; i++) {
        smbus_write_byte_data(base, addr, 0x20, buf40[i]);
    }
    uint8_t expected_crc = crc8_corsair(buf40, 40);
    int hw_crc = smbus_read_byte_data(base, addr, 0x42);
    if (hw_crc < 0 || (uint8_t)hw_crc == expected_crc) {
        smbus_write_byte_data(base, addr, 0x82, 0x02);
        corsair_wait_ready(base, addr);
    }
    return 0;
}

int main(int argc, char **argv) {
    /* Elevate effective UID to root if SUID bit is set */
    if (geteuid() == 0) {
        setuid(0);
    }

    if (argc >= 2 && strcmp(argv[1], "install_suid") == 0) {
        char self_path[1024];
        ssize_t len = readlink("/proc/self/exe", self_path, sizeof(self_path) - 1);
        if (len > 0) {
            self_path[len] = '\0';
            chown(self_path, 0, 0);
            chmod(self_path, 04755);
        }
    }

    if (ioperm(PIIX4_SMB_BASE_PRIMARY, 0x28, 1) != 0) {
        fprintf(stderr, "{\"error\": \"permission_denied\", \"message\": \"Root privileges (ioperm) required for direct 0x0B00 SMBus I/O\"}\n");
        return 1;
    }

    if (argc >= 2 && (strcmp(argv[1], "scan") == 0 || strcmp(argv[1], "install_suid") == 0)) {
        printf("{\"port\": \"0x0B00\", \"suid_installed\": %s, \"devices\": [",
               (geteuid() == 0) ? "true" : "false");
        int first = 1;
        uint8_t candidates[] = {0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F, 0x58, 0x59, 0x5A, 0x5B};
        for (size_t i = 0; i < sizeof(candidates); i++) {
            uint8_t addr = candidates[i];
            int r43 = smbus_read_byte_data(PIIX4_SMB_BASE_PRIMARY, addr, 0x43);
            int r44 = smbus_read_byte_data(PIIX4_SMB_BASE_PRIMARY, addr, 0x44);
            int r00 = smbus_read_byte_data(PIIX4_SMB_BASE_PRIMARY, addr, 0x00);
            if (r00 >= 0 || r43 >= 0) {
                if (!first) printf(", ");
                printf("{\"addr\": \"0x%02x\", \"reg0\": %d, \"reg43\": %d, \"reg44\": %d}", addr, r00, r43, r44);
                first = 0;
            }
        }
        printf("]}\n");
        fflush(stdout);
        return 0;
    }

    if (argc >= 2 && strcmp(argv[1], "daemon") == 0) {
        printf("{\"status\": \"daemon_ready\", \"port\": \"0x0B00\"}\n");
        fflush(stdout);
        char line[1024];
        while (fgets(line, sizeof(line), stdin) != NULL) {
            if (strncmp(line, "ram ", 4) == 0) {
                char *p = line + 4;
                uint8_t addr = (uint8_t)strtol(p, &p, 0);
                uint8_t rgb[30];
                memset(rgb, 0, sizeof(rgb));
                for (int i = 0; i < 30; i++) {
                    rgb[i] = (uint8_t)strtol(p, &p, 10);
                }
                write_corsair_ddr5_10leds(PIIX4_SMB_BASE_PRIMARY, addr, rgb);
            } else if (strncmp(line, "quit", 4) == 0) {
                break;
            }
        }
        return 0;
    }

    if (argc >= 6 && strcmp(argv[1], "set_ram_rgb") == 0) {
        uint8_t addr = (uint8_t)strtol(argv[2], NULL, 0);
        uint8_t r = (uint8_t)atoi(argv[3]);
        uint8_t g = (uint8_t)atoi(argv[4]);
        uint8_t b = (uint8_t)atoi(argv[5]);
        uint8_t br = (argc >= 7) ? (uint8_t)atoi(argv[6]) : 255;
        uint8_t sr = (uint8_t)(((int)r * (int)br) / 255);
        uint8_t sg = (uint8_t)(((int)g * (int)br) / 255);
        uint8_t sb = (uint8_t)(((int)b * (int)br) / 255);
        uint8_t rgb[30];
        for (int i = 0; i < 10; i++) {
            rgb[i * 3 + 0] = sr;
            rgb[i * 3 + 1] = sg;
            rgb[i * 3 + 2] = sb;
        }
        write_corsair_ddr5_10leds(PIIX4_SMB_BASE_PRIMARY, addr, rgb);
        printf("{\"status\": \"ok\", \"addr\": \"0x%02x\"}\n", addr);
        return 0;
    }

    return 0;
}
