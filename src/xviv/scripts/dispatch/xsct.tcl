# =============================================================================
# scripts/xviv_xsct.tcl  -  XSCT dispatcher for xviv
#
# Invoked exclusively by the Python controller (xviv).  Do not call directly.
# xsct is a separate Tcl shell shipped with Vivado/Vitis; it exposes the
# "hsi" (Hardware Software Interface) and hardware-server client APIs.
#
# Usage:
#   xsct xviv_xsct.tcl <command> [args...]
#
# Commands:
#   create_platform  <xsa> <cpu> <os> <bsp_dir>
#       Generate a BSP from an XSA hardware description using hsi.
#       Equivalent to: hsi open_hw_design / create_sw_design / generate_bsp.
#
#   create_app  <xsa> <cpu> <os> <template> <app_dir>
#       Scaffold an application directory from a named Vitis template using
#       hsi::generate_app.  User sources are copied by Python after this exits.
#
#   program  <bitstream> <elf_or_empty> <hw_server>
#       Connect to hw_server, download the bitstream to the FPGA, then
#       (optionally) reset the MicroBlaze and load the ELF via JTAG.
#
#   processor_reset  <hw_server>
#       Soft-reset the MicroBlaze (rst -processor) then resume execution.
#
#   processor_status  <hw_server>
#       Print JTAG targets, processor state, and general-purpose registers.
#
#   jtag_uart  <hw_server>
#       Stream JTAG UART output to stdout in real time.
#
# =============================================================================

if {$::argc < 1} {
    puts stderr "XVIV XSCT ERROR: Usage: xsct xviv_xsct.tcl <command> \[args...\]"
    exit 1
}

set _xsct_cmd [lindex $::argv 0]

# =============================================================================
# Shared utilities
# =============================================================================

# ---------------------------------------------------------------------------
# xsct_die  -  print a structured error and exit 1.
# ---------------------------------------------------------------------------
proc xsct_die {msg} {
    puts stderr ""
    puts stderr "XVIV XSCT ERROR: $msg"
    puts stderr "  command: $::_xsct_cmd"
    puts stderr ""
    exit 1
}

# ---------------------------------------------------------------------------
# xsct_connect  -  connect to hw_server.
#
# Passes -url only when the caller supplies a non-default address so that
# the common case of localhost:3121 uses the implicit default (avoids an
# extra round-trip to resolve the address string).
# ---------------------------------------------------------------------------
proc xsct_connect {hw_server} {
    if {$hw_server eq "" || $hw_server eq "localhost:3121"} {
        connect
    } else {
        connect -url tcp:$hw_server
    }
    puts "INFO: Connected to hw_server: $hw_server"
}

# ---------------------------------------------------------------------------
# xsct_select_fpga  -  select the first Xilinx FPGA target visible on JTAG.
#
# Prints the full target list so it appears in the log regardless of whether
# the filter succeeds.  Exits with a descriptive error when no FPGA is found.
# ---------------------------------------------------------------------------
proc xsct_select_fpga {} {
    set tlist [targets]
    puts "INFO: JTAG targets:\n$tlist"

    # Xilinx FPGA devices appear as "xc7*", "xcvu*", "xczu*", etc.
    # The -filter selects AND switches to that target in one call.
    if {[catch {targets -set -filter {name =~ "xc*"}} err]} {
        xsct_die "No FPGA target found on JTAG.\n  $err\n  Is the FPGA powered and connected?"
    }
    puts "INFO: FPGA target selected"
	puts [targets]
}

# ---------------------------------------------------------------------------
# xsct_select_mb  -  select the first MicroBlaze processor target.
# ---------------------------------------------------------------------------
proc xsct_select_mb {} {
    if {[catch {targets -set -filter {name =~ "MicroBlaze #0*"}} err]} {
        xsct_die "No MicroBlaze target found.\n  $err\n  Is the FPGA programmed?"
    }
    puts "INFO: MicroBlaze target selected"
	puts [targets]
}

# =============================================================================
# Command: create_platform  <xsa> <cpu> <os> <bsp_dir>
#
# Generates a Board Support Package from an XSA hardware description using
# Xilinx HSI (Hardware Software Interface).  The resulting BSP directory
# contains a Makefile and the libxil sources; 'platform-build' compiles them.
# =============================================================================
proc cmd_create_platform {xsa cpu os_name bsp_dir} {
    if {![file exists $xsa]} {
        xsct_die "XSA not found: $xsa"
    }

    puts "INFO: Generating BSP platform"
    puts "INFO:   XSA    : $xsa"
    puts "INFO:   CPU    : $cpu"
    puts "INFO:   OS     : $os_name"
    puts "INFO:   BSP dir: $bsp_dir"

    file mkdir $bsp_dir

    set hw [hsi::open_hw_design $xsa]
    hsi::create_sw_design bsp_design -proc $cpu -os $os_name

    hsi::set_property CONFIG.stdout mdm_1 [hsi::get_os]
    hsi::set_property CONFIG.stdin  mdm_1 [hsi::get_os]

    hsi::generate_bsp -dir $bsp_dir


    hsi::close_hw_design $hw

    puts "INFO: BSP generated at $bsp_dir"
    exit 0
}

# =============================================================================
# Command: create_app  <xsa> <cpu> <os> <template> <app_dir>
#
# Scaffolds an application from one of Vitis' built-in templates.
# Common templates: empty_application, hello_world, lwip_echo_server,
#                   xilkernel_thread_demo, zynq_fsbl, etc.
# After this command exits, Python copies user sources into <app_dir>/src/.
# =============================================================================
proc cmd_create_app {xsa cpu os_name template app_dir} {
    if {![file exists $xsa]} {
        xsct_die "XSA not found: $xsa"
    }

    puts "INFO: Scaffolding application"
    puts "INFO:   XSA     : $xsa"
    puts "INFO:   CPU     : $cpu"
    puts "INFO:   OS      : $os_name"
    puts "INFO:   Template: $template"
    puts "INFO:   App dir : $app_dir"

    file mkdir $app_dir

    set hw [hsi::open_hw_design $xsa]
    hsi::generate_app \
        -hw   $hw \
        -os   $os_name \
        -proc $cpu \
        -app  $template \
        -dir  $app_dir
    hsi::close_hw_design $hw

    puts "INFO: Application scaffolded at $app_dir"
    exit 0
}

# =============================================================================
# Command: program  <bitstream> <elf_or_empty> <hw_server>
#
# 1. Connect to hw_server.
# 2. Select the FPGA target and download the bitstream.
# 3. If an ELF is supplied: select the MicroBlaze, soft-reset it,
#    download the ELF, and resume execution.
# =============================================================================
proc cmd_program {bitstream elf hw_server} {
    if {![file exists $bitstream]} {
        xsct_die "Bitstream not found: $bitstream"
    }
    if {$elf ne "" && ![file exists $elf]} {
        xsct_die "ELF not found: $elf"
    }

    puts "INFO: Programming FPGA"
    puts "INFO:   Bitstream : $bitstream"
    if {$elf ne ""} { puts "INFO:   ELF       : $elf" }
    puts "INFO:   hw_server : $hw_server"

    xsct_connect $hw_server

    # ---- Download bitstream ----
    xsct_select_fpga
    fpga -f $bitstream
    puts "INFO: Bitstream programmed successfully"

    # ---- Download ELF (optional) ----
    if {$elf ne ""} {
        # Give the fabric a moment to come out of reset before switching targets.
        after 500

        xsct_select_mb
        rst -processor
        dow $elf
        puts "INFO: ELF loaded: [file tail $elf]"
        con
        puts "INFO: Processor running"
    }

    disconnect
    exit 0
}

# =============================================================================
# Command: processor_reset  <hw_server>
#
# Performs a software reset of the MicroBlaze without reprogramming the FPGA.
# Useful after reflashing the ELF without changing the bitstream.
# =============================================================================
proc cmd_processor_reset {hw_server} {
    puts "INFO: Resetting embedded processor"
    puts "INFO:   hw_server : $hw_server"

    xsct_connect $hw_server

    xsct_select_mb
    rst -processor
    puts "INFO: Processor reset"
    con
    puts "INFO: Processor running"

    disconnect
    exit 0
}

# =============================================================================
# Command: processor_status  <hw_server>
#
# Prints:
#   - All JTAG targets (IDs, names, state)
#   - MicroBlaze execution state (running / stopped / error)
#   - General-purpose registers (rrd) when the processor is halted
# =============================================================================
proc cmd_processor_status {hw_server} {
    puts "INFO: Processor status"
    puts "INFO:   hw_server : $hw_server"

    xsct_connect $hw_server

    puts "\n=== JTAG Targets ==="
    puts [targets]

    # Attempt to read MicroBlaze state; non-fatal if processor is running.
    if {[catch {xsct_select_mb} err]} {
        puts "WARN: Could not select MicroBlaze target: $err"
        disconnect
        exit 0
    }

    puts "\n=== Processor State ==="
    if {[catch {puts [state]} err]} {
        puts "  (could not read state: $err)"
    }

    puts "\n=== General-Purpose Registers ==="
    if {[catch {puts [rrd]} err]} {
        puts "  (registers unavailable - processor may be running)"
        puts "  Hint: use 'xviv processor --reset' to halt and inspect."
    }

    disconnect
    exit 0
}

# =============================================================================
# Command: jtag_uart  <hw_server>
#
# Streams JTAG UART output from the MicroBlaze to stdout in real time.
# Press Ctrl-C to stop.
#
# Implementation notes:
#   readjtaguart -start -handle <proc>
#     Registers <proc> as a callback invoked by the xsct event loop each time
#     the MDM JTAG UART FIFO contains data.  The callback receives the raw
#     data string (may contain multiple characters per call).
#
#   "while {1} { after 100 }"
#     Keeps the xsct Tcl event loop alive.  The "after 100" yields for 100 ms
#     on each iteration, allowing the event loop to fire the readjtaguart
#     callback without busy-spinning.  Ctrl-C raises an error caught by the
#     outer catch, triggering a clean disconnect.
#
# Prerequisites:
#   - MDM IP in the BD with C_USE_UART = 1
#   - hw_server running and FPGA programmed
#   - Firmware using xil_printf() or outbyte() to the JTAG UART
# =============================================================================
proc cmd_jtag_uart {hw_server} {
    puts "INFO: JTAG UART monitor starting"
    puts "INFO:   hw_server : $hw_server"
    puts "INFO:   Press Ctrl-C to stop\n"
    puts "--- JTAG UART output ---"

    xsct_connect $hw_server

    if {[catch {targets -set -filter {name =~ "MicroBlaze Debug Module*"}} err]} {
        xsct_die "No MDM target found.\n  $err"
    }
    puts "INFO: MDM target selected"
    puts [targets]

    # Check if readjtaguart is even available
    puts "INFO: readjtaguart available: [info commands readjtaguart]"

    # Try capturing to a temp file instead of stdout to rule out buffering
    set fh [open /tmp/jtag_uart.log w]
    puts "INFO: Opened log file handle: $fh"

    if {[catch {readjtaguart -start -handle $fh} err]} {
        puts "ERROR: readjtaguart failed: $err"
        exit 1
    }
    puts "INFO: JTAG UART capture active"
    puts "INFO: Tailing /tmp/jtag_uart.log in parallel..."

    if {[catch {
        set i 0
        while {1} {
            after 100
            # Every second, check if anything landed in the file
            incr i
            if {$i >= 10} {
                set i 0
                flush $fh
                puts "INFO: heartbeat - checking log..."
                set rh [open /tmp/jtag_uart.log r]
                puts "FILE CONTENTS: [read $rh]"
                close $rh
            }
        }
    } err]} {
        puts "\nINFO: Monitor interrupted: $err"
    }

    catch { readjtaguart -stop }
    catch { close $fh }
    catch { disconnect }
    exit 0
}

# =============================================================================
# Dispatch
# =============================================================================
switch -- $_xsct_cmd {

    create_platform {
        if {$::argc < 5} {
            xsct_die "create_platform requires: <xsa> <cpu> <os> <bsp_dir>"
        }
        cmd_create_platform \
            [lindex $::argv 1] \
            [lindex $::argv 2] \
            [lindex $::argv 3] \
            [lindex $::argv 4]
    }

    create_app {
        if {$::argc < 6} {
            xsct_die "create_app requires: <xsa> <cpu> <os> <template> <app_dir>"
        }
        cmd_create_app \
            [lindex $::argv 1] \
            [lindex $::argv 2] \
            [lindex $::argv 3] \
            [lindex $::argv 4] \
            [lindex $::argv 5]
    }

    program {
        if {$::argc < 4} {
            xsct_die "program requires: <bitstream> <elf_or_empty> <hw_server>"
        }
        cmd_program \
            [lindex $::argv 1] \
            [lindex $::argv 2] \
            [lindex $::argv 3]
    }

    processor_reset {
        if {$::argc < 2} {
            xsct_die "processor_reset requires: <hw_server>"
        }
        cmd_processor_reset [lindex $::argv 1]
    }

    processor_status {
        if {$::argc < 2} {
            xsct_die "processor_status requires: <hw_server>"
        }
        cmd_processor_status [lindex $::argv 1]
    }

    jtag_uart {
        if {$::argc < 2} {
            xsct_die "jtag_uart requires: <hw_server>"
        }
        cmd_jtag_uart [lindex $::argv 1]
    }

    default {
        puts stderr "XVIV XSCT ERROR: Unknown command '$_xsct_cmd'"
        puts stderr "Valid commands:"
        puts stderr "  create_platform  create_app"
        puts stderr "  program"
        puts stderr "  processor_reset  processor_status"
        puts stderr "  jtag_uart"
        exit 1
    }
}