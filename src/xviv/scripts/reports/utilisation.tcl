# =============================================================================
#  xviv_print_resources  v5
#
#  Pretty-prints FPGA resource utilisation in the Vivado TCL console.
#  Supports two display modes and multi-coloured segmented progress bars
#  that break down each resource category by primitive sub-type.
#  Bars and dividers dynamically adjust to the current terminal width.
#
#  Usage:
#    source xviv_print_resources.tcl
#    xviv_print_resources           ;# detailed (default) — full sub-type rows
#    xviv_print_resources concise   ;# compact — one bar per group + colour key
#    xviv_print_resources extra     ;# ultra-compact — bars and timing only
#
#  Segmented bars are used wherever a resource has meaningful sub-types:
#    LUTs       → LUT1 / LUT2 / LUT3 / LUT4 / LUT5 / LUT6 / LUT6_2
#    Flip-flops → FDRE / FDCE / FDPE / FDSE
#    SRLs       → SRL16E / SRLC32E  (capacity = SLICEM × LUTs-per-SLICEM)
#    BRAMs      → BRAM36 / BRAM18 (as BRAM36-equivalents)
#    I/O Bufs   → IBUF / OBUF / IOBUF / BIBUF
# =============================================================================


# --- Terminal geometry -------------------------------------------------------
proc _xvr_term_width {} {
    set w 0
    catch { set w [lindex [exec stty size] 1] }
    if {$w <= 0} { catch { set w [expr {int($::env(COLUMNS))}] } }
    if {$w < 80}  { set w 120 }
    return $w
}

proc _xvr_vislen {s} {
    regsub -all {\033\[[0-9;]*m} $s "" plain
    return [string length $plain]
}


# --- ANSI colour / style helpers ---------------------------------------------
proc _xvr_c    {n s} { return "\033\[${n}m${s}\033\[0m" }
proc _xvr_bold {s}   { return [_xvr_c 1  $s] }
proc _xvr_dim  {s}   { return [_xvr_c 2  $s] }
proc _xvr_grn  {s}   { return [_xvr_c 92 $s] }
proc _xvr_yel  {s}   { return [_xvr_c 93 $s] }
proc _xvr_red  {s}   { return [_xvr_c 91 $s] }
proc _xvr_cyn  {s}   { return [_xvr_c 96 $s] }
proc _xvr_mag  {s}   { return [_xvr_c 95 $s] }
proc _xvr_blu  {s}   { return [_xvr_c 94 $s] }


# --- Single-colour utilisation bar -------------------------------------------
#   Colour: green < 75 %  ·  yellow 75–89 %  ·  red ≥ 90 %
proc _xvr_bar {used total} {
    set W $::_xvr_BW
    if {$total <= 0 || $used <= 0} {
        return "\033\[90m[string repeat \u2591 $W]\033\[0m"
    }
    
    set pct [expr {double($used) / $total}]
    if {$pct > 1.0} { set pct 1.0 }

    # Non-linear boost to inflate the visual footprint of small values
    set boosted_pct [expr {sqrt($pct)}]
    set fill [expr {int(round($boosted_pct * $W))}]

    # Enforce minimum 1 block if used > 0
    if {$fill < 1} { set fill 1 }
    # Guarantee at least 1 empty block if not fully occupied
    if {$pct < 1.0 && $fill >= $W} { set fill [expr {$W - 1}] }

    set empty [expr {$W - $fill}]
    
    if      {$pct >= 0.90} { set col 91 } \
    elseif  {$pct >= 0.75} { set col 93 } \
    else                    { set col 92 }
    
    return "\033\[${col}m[string repeat \u2588 $fill]\033\[90m[string repeat \u2591 $empty]\033\[0m"
}


# --- Segmented / stacked bar -------------------------------------------------
proc _xvr_segbar {segments total} {
    set W $::_xvr_BW

    # total == 0  →  unknown capacity; dim empty bar
    if {$total == 0} { return "\033\[90m[string repeat \u2591 $W]\033\[0m" }

    set used 0
    foreach seg $segments { incr used [lindex $seg 0] }
    if {$used <= 0} { return "\033\[90m[string repeat \u2591 $W]\033\[0m" }

    # total < 0  →  proportional breakdown
    if {$total < 0} { set total $used }

    # 1. Calculate the overall inflated width for the whole resource
    set pct [expr {double($used) / $total}]
    if {$pct > 1.0} { set pct 1.0 }
    
    set boosted_pct [expr {sqrt($pct)}]
    set allocated_w [expr {int(round($boosted_pct * $W))}]

    if {$allocated_w < 1} { set allocated_w 1 }

    # Guarantee at least 1 empty block if not fully occupied
    set max_allowed $W
    if {$pct < 1.0} { 
        set max_allowed [expr {$W - 1}] 
        if {$allocated_w > $max_allowed} { set allocated_w $max_allowed }
    }

    # 2. Distribute the blocks among the sub-types
    set bar ""
    set filled 0
    foreach seg $segments {
        set cnt [lindex $seg 0]
        set col [lindex $seg 1]
        if {$cnt <= 0} { continue }

        # Calculate share based on the used portion
        set share [expr {double($cnt) / $used}]
        set chars [expr {int(round($share * $allocated_w))}]

        # Force a minimum of 1 block so tiny values (like FDPE) don't disappear
        if {$chars < 1} { set chars 1 }

        # Hard cap to ensure the terminal layout never breaks
        if {$filled + $chars > $max_allowed} { 
            set chars [expr {$max_allowed - $filled}] 
        }

        if {$chars > 0} {
            append bar "\033\[${col}m[string repeat \u2588 $chars]\033\[0m"
            incr filled $chars
        }
    }
    
    # 3. Fill the remainder of the terminal width with empty space
    if {$filled < $W} {
        append bar "\033\[90m[string repeat \u2591 [expr {$W - $filled}]]\033\[0m"
    }
    return $bar
}


# --- Colour legend builder ---------------------------------------------------
proc _xvr_legend {pairs {prefix "       "}} {
    set out $prefix
    foreach p $pairs {
        set lbl [lindex $p 0]
        set col [lindex $p 1]
        append out "\033\[${col}m\u2588\033\[0m\033\[2m${lbl}\033\[0m  "
    }
    return $out
}


# --- Structural / layout helpers ---------------------------------------------
proc _xvr_inner_w {} { return [expr {$::_xvr_TW - 4}] }

proc _xvr_sep {} {
    puts "  \033\[2m[string repeat \u00b7 [_xvr_inner_w]]\033\[0m"
}
proc _xvr_div {} {
    puts "  [string repeat \u2500 [_xvr_inner_w]]"
}
proc _xvr_section {title} {
    puts ""
    puts "  \033\[1m[string toupper $title]\033\[0m"
    _xvr_div
}
proc _xvr_col_hdr {} {
    set bar_hdr [format "%-*s" $::_xvr_BW "Utilisation"]
    puts "\033\[2m[format "  %-26s  %7s  %11s  %s  %s" \
          Resource Used "/ Total" $bar_hdr %]\033\[0m"
    _xvr_sep
}


# --- Resource row primitives -------------------------------------------------

proc _xvr_rowseg {label used total segments} {
    set lbl [format "  %-26s" $label]
    set cnt [format "  %7d" $used]

    if {$total > 0} {
        set pct_v [expr {double($used) / $total * 100.0}]
        set tot_s [format "  %9s" "/ $total"]
        if {[llength $segments] > 0} {
            set bar_s "  [_xvr_segbar $segments $total]"
        } else {
            set bar_s "  [_xvr_bar $used $total]"
        }
        set pct_s [format "  %5.1f%%" $pct_v]
    } elseif {[llength $segments] > 0} {
        # total == 0 or negative: show bar (segbar handles the sentinel),
        # but suppress the / Total and % columns
        set tot_s [format "  %9s" ""]
        set bar_s "  [_xvr_segbar $segments $total]"
        set pct_s ""
    } else {
        set tot_s "";  set bar_s "";  set pct_s ""
    }
    puts "${lbl}${cnt}${tot_s}${bar_s}${pct_s}"
}

proc _xvr_row {label used {total 0}} {
    _xvr_rowseg $label $used $total {}
}

proc _xvr_subrow {label used {col ""}} {
    if {$col ne ""} {
        set bullet "\033\[${col}m\u2588\033\[0m"
    } else {
        set bullet "\033\[2m\u00b7\033\[0m"
    }
    puts "\033\[2m    $bullet [format "%-24s" $label][format "%7d" $used]\033\[0m"
}


# =============================================================================
#  Main entry point
# =============================================================================
proc xviv_print_resources {{mode "detailed"}} {

    # -- Terminal geometry (set globals used by all helper procs) --------------
    set ::_xvr_TW [_xvr_term_width]
    set ::_xvr_BW [expr {max(16, $::_xvr_TW - 60)}]
    set TW $::_xvr_TW

    # Define our display modes
    set is_extra    [expr {$mode eq "extra" || $mode eq "extra_concise"}]
    set is_detailed [expr {$mode ne "concise" && !$is_extra}]

    # -- Gather all primitives once --------------------------------------------
    set all_prims   [get_cells -quiet -hier -filter {IS_PRIMITIVE==1}]
    set total_prims [llength $all_prims]

    # -- Per-type counts -------------------------------------------------------
    foreach {var flt} {
        lut1    {IS_PRIMITIVE==1 && REF_NAME==LUT1}
        lut2    {IS_PRIMITIVE==1 && REF_NAME==LUT2}
        lut3    {IS_PRIMITIVE==1 && REF_NAME==LUT3}
        lut4    {IS_PRIMITIVE==1 && REF_NAME==LUT4}
        lut5    {IS_PRIMITIVE==1 && REF_NAME==LUT5}
        lut6    {IS_PRIMITIVE==1 && REF_NAME==LUT6}
        lut6_2  {IS_PRIMITIVE==1 && REF_NAME==LUT6_2}
        fdre    {IS_PRIMITIVE==1 && REF_NAME==FDRE}
        fdce    {IS_PRIMITIVE==1 && REF_NAME==FDCE}
        fdpe    {IS_PRIMITIVE==1 && REF_NAME==FDPE}
        fdse    {IS_PRIMITIVE==1 && REF_NAME==FDSE}
        latch   {IS_PRIMITIVE==1 && REF_NAME =~ LD*}
        srl16e  {IS_PRIMITIVE==1 && REF_NAME==SRL16E}
        srlc32e {IS_PRIMITIVE==1 && REF_NAME==SRLC32E}
        carry   {IS_PRIMITIVE==1 && REF_NAME =~ CARRY*}
        muxf7   {IS_PRIMITIVE==1 && REF_NAME==MUXF7}
        muxf8   {IS_PRIMITIVE==1 && REF_NAME==MUXF8}
        dsp     {IS_PRIMITIVE==1 && REF_NAME =~ DSP48*}
        bram18  {IS_PRIMITIVE==1 && REF_NAME =~ RAMB18*}
        bram36  {IS_PRIMITIVE==1 && REF_NAME =~ RAMB36*}
        ram32m  {IS_PRIMITIVE==1 && REF_NAME =~ RAM32*}
        ram64m  {IS_PRIMITIVE==1 && REF_NAME =~ RAM64*}
        bufg    {IS_PRIMITIVE==1 && REF_NAME =~ BUFG*}
        bufr    {IS_PRIMITIVE==1 && REF_NAME =~ BUFR*}
        pll     {IS_PRIMITIVE==1 && REF_NAME =~ PLLE*}
        mmcm    {IS_PRIMITIVE==1 && REF_NAME =~ MMCME*}
        ps7     {IS_PRIMITIVE==1 && REF_NAME==PS7}
        ibuf    {IS_PRIMITIVE==1 && REF_NAME =~ IBUF*}
        obuf    {IS_PRIMITIVE==1 && REF_NAME =~ OBUF*}
        iobuf   {IS_PRIMITIVE==1 && REF_NAME =~ IOBUF*}
        bibuf   {IS_PRIMITIVE==1 && REF_NAME==BIBUF}
    } {
        set $var [llength [get_cells -quiet -hier -filter $flt]]
    }

    # -- Derived totals --------------------------------------------------------
    set lut_total  [expr {$lut1+$lut2+$lut3+$lut4+$lut5+$lut6+$lut6_2}]
    set ff_total   [expr {$fdre+$fdce+$fdpe+$fdse}]
    set srl_total  [expr {$srl16e+$srlc32e}]
    set io_total   [expr {$ibuf+$obuf+$iobuf+$bibuf}]
    set bram18_eq  [expr {int(ceil($bram18 / 2.0))}]
    set bram_eq    [expr {$bram36 + $bram18_eq}]
    set fixed_cnt  [llength [get_cells -quiet -hier -filter {IS_LOC_FIXED==1}]]
    set blackboxes [get_cells -quiet -hier -filter {IS_BLACKBOX==1 && IS_PRIMITIVE==0}]
    set bb_count   [llength $blackboxes]

    # -- Primitive type inventory ----------------------------------------------
    set ref_set {}
    foreach r [get_property REF_NAME $all_prims] {
        if {[lsearch -exact $ref_set $r] == -1} { lappend ref_set $r }
    }

    # -- Clock regions ---------------------------------------------------------
    set cr_set {}
    # Get the physical sites occupied by the primitives
    set used_sites [get_sites -quiet -of_objects $all_prims]
    
    # Extract the clock region from the sites instead of the cells
    foreach v [get_property CLOCK_REGION $used_sites] {
        if {$v ne "" && [lsearch -exact $cr_set $v] == -1} {
            lappend cr_set $v
        }
    }
    set cr_count [llength [lsort $cr_set]]

    # -- Device capacity & identification -------------------------------------
    set cap_lut 0;  set cap_ff 0;  set cap_srl 0
    set cap_dsp 0;  set cap_bram36 0;  set cap_io 0
    set p_name "";  set p_speed "";  set p_family "";  set p_board ""

    catch {
        set part_obj [get_parts [get_property PART [current_project]]]
        set p_name   [get_property NAME   $part_obj]
        set p_speed  [get_property SPEED  $part_obj]
        set p_family [get_property FAMILY $part_obj]

        # LUT capacity
        foreach prop {LUT_ELEMENTS LUT LUTS} {
            if {![catch {set v [get_property $prop $part_obj]}] && $v > 0} {
                set cap_lut $v; break
            }
        }

        # FF capacity
        foreach prop {FLIPFLOPS FF FFS FF_ELEMENTS} {
            if {![catch {set v [get_property $prop $part_obj]}] && $v > 0} {
                set cap_ff $v; break
            }
        }

        catch { set cap_dsp    [get_property DSP          $part_obj] }
        catch { set cap_bram36 [get_property BLOCK_RAMS   $part_obj] }
        catch { set cap_io     [get_property IO_PIN_COUNT $part_obj] }
    }
    catch { set p_board [get_property BOARD_PART [current_project]] }
    set cap_bram18 [expr {$cap_bram36 * 2}]

    # -- SRL capacity — device-agnostic ---------------------------------------
    catch {
        set slicem_sites [get_sites -quiet -filter {SITE_TYPE==SLICEM}]
        if {[llength $slicem_sites] > 0} {
            set luts_per [llength [get_bels -quiet \
                -of_objects [lindex $slicem_sites 0] \
                -filter {TYPE =~ *LUT*}]]
            if {$luts_per <= 0} { set luts_per 4 }   ;# safe fallback
            set cap_srl [expr {[llength $slicem_sites] * $luts_per}]
        }
    }

    # -- Clocks and Fmax -------------------------------------------------------
    set clock_rows {}
    foreach clk [get_clocks -quiet] {
        set period [get_property PERIOD $clk]
        if {$period eq "" || $period <= 0} { continue }
        set cname [get_property NAME $clk]
        set wns ""
        catch {
            set wp [get_timing_paths -quiet -max_paths 1 -nworst 1 \
                        -setup -filter "ENDPOINT_CLOCK == $cname"]
            if {[llength $wp]} { set wns [get_property SLACK $wp] }
        }
        lappend clock_rows [list $cname $period $wns]
    }

    # -- Segment colour assignments --------------------------------------------
    set lut_segs [list \
        [list $lut1   96] [list $lut2   92] [list $lut3   93] \
        [list $lut4   95] [list $lut5   94] [list $lut6   91] \
        [list $lut6_2 97]]
    set lut_legend [list \
        {LUT1 96} {LUT2 92} {LUT3 93} {LUT4 95} {LUT5 94} {LUT6 91} {LUT6_2 97}]

    set ff_segs   [list [list $fdre 92] [list $fdce 93] [list $fdpe 94] [list $fdse 95]]
    set ff_legend [list {FDRE 92} {FDCE 93} {FDPE 94} {FDSE 95}]

    set srl_segs   [list [list $srl16e 92] [list $srlc32e 95]]
    set srl_legend [list {SRL16E 92} {SRLC32E 95}]

    set bram_segs   [list [list $bram36 94] [list $bram18_eq 96]]
    set bram_legend [list {BRAM36 94} {BRAM18→eq 96}]

    set io_segs   [list [list $ibuf 92] [list $obuf 93] [list $iobuf 94] [list $bibuf 95]]
    set io_legend [list {IBUF 92} {OBUF 93} {IOBUF 94} {BIBUF 95}]


    # ==========================================================================
    #  H E A D E R
    # ==========================================================================
    set dline [string repeat \u2550 [expr {$TW - 2}]]
    set sline [string repeat \u2500 [expr {$TW - 2}]]

    set title "VIVADO RESOURCE UTILISATION REPORT"
    set tpad  [expr {max(0, ($TW - 2 - [string length $title]) / 2)}]

    set info_parts {}
    if {$p_name   ne ""} { lappend info_parts "PART  [_xvr_bold $p_name]" }
    if {$p_speed  ne ""} { lappend info_parts "SPEED GRADE  [_xvr_bold $p_speed]" }
    if {$p_family ne ""} { lappend info_parts "FAMILY  [_xvr_bold [string toupper $p_family]]" }
    set info_line1 [join $info_parts "   \u00b7   "]
    set info_line2 ""
    if {$p_board ne ""} { set info_line2 "BOARD  [_xvr_bold $p_board]" }
    set info_line3 "PRIMITIVES  [_xvr_bold $total_prims]"
    set iprefix "    "

    puts ""
    puts "  \033\[1m$dline\033\[0m"
    puts "[string repeat " " [expr {$tpad + 2}]][_xvr_bold $title]"
    puts "  \033\[2m$sline\033\[0m"
    if {$info_line1 ne ""} { puts "${iprefix}${info_line1}" }
    if {$info_line2 ne ""} { puts "${iprefix}${info_line2}" }
    puts "${iprefix}${info_line3}"
    puts "  \033\[1m$dline\033\[0m"


    # ==========================================================================
    if {$is_detailed} {
    # --------------------------------------------------------------------------
    #  D E T A I L E D   M O D E
    # --------------------------------------------------------------------------

        # -- Logic -------------------------------------------------------------
        _xvr_section "Logic"
        _xvr_col_hdr

        _xvr_rowseg "LUTs (total)" $lut_total $cap_lut $lut_segs
        puts [_xvr_legend $lut_legend "                             "]
        _xvr_subrow "LUT1"   $lut1   96
        _xvr_subrow "LUT2"   $lut2   92
        _xvr_subrow "LUT3"   $lut3   93
        _xvr_subrow "LUT4"   $lut4   95
        _xvr_subrow "LUT5"   $lut5   94
        _xvr_subrow "LUT6"   $lut6   91
        _xvr_subrow "LUT6_2" $lut6_2 97
        _xvr_sep

        _xvr_rowseg "Flip-flops (total)" $ff_total $cap_ff $ff_segs
        puts [_xvr_legend $ff_legend "                             "]
        _xvr_subrow "FDRE"   $fdre   92
        _xvr_subrow "FDCE"   $fdce   93
        _xvr_subrow "FDPE"   $fdpe   94
        _xvr_subrow "FDSE"   $fdse   95
        _xvr_sep

        # SRLs — cap_srl is SLICEM × LUTs-per-SLICEM (device-agnostic)
        _xvr_rowseg "SRLs" $srl_total $cap_srl $srl_segs
        puts [_xvr_legend $srl_legend "                             "]
        _xvr_subrow "SRL16E"  $srl16e  92
        _xvr_subrow "SRLC32E" $srlc32e 95
        _xvr_sep

        _xvr_row "Carry chains"   $carry
        _xvr_row "MUXF7"          $muxf7
        _xvr_row "MUXF8"          $muxf8

        if {$latch > 0} {
            puts ""
            puts "  [_xvr_yel "\u25b2  Warning: $latch inferred latch(es) \u2014 verify intent"]"
        }

        # -- Memory & DSP ------------------------------------------------------
        _xvr_section "Memory & DSP"
        _xvr_col_hdr

        _xvr_row "DSP48" $dsp $cap_dsp
        _xvr_sep

        _xvr_rowseg "BRAM (BRAM36-eq)" $bram_eq $cap_bram36 $bram_segs
        puts [_xvr_legend $bram_legend "                             "]
        _xvr_subrow "BRAM36 (used)"    $bram36 94
        _xvr_subrow "BRAM18 (used)"    $bram18 96
        puts "[_xvr_dim "       \u2261  ${bram18} \u00d7 BRAM18  =  ${bram18_eq} BRAM36-eq"]"
        _xvr_sep

        _xvr_row "Dist RAM (RAM32M)"  $ram32m
        _xvr_row "Dist RAM (RAM64M)"  $ram64m

        # -- Clocking & I/O ----------------------------------------------------
        _xvr_section "Clocking & I/O"
        _xvr_col_hdr

        _xvr_row "BUFG"  $bufg
        _xvr_row "BUFR"  $bufr
        _xvr_row "PLL"   $pll
        _xvr_row "MMCM"  $mmcm
        _xvr_sep

        _xvr_rowseg "I/O Buffers" $io_total $cap_io $io_segs
        puts [_xvr_legend $io_legend "                             "]
        _xvr_subrow "IBUF"  $ibuf  92
        _xvr_subrow "OBUF"  $obuf  93
        _xvr_subrow "IOBUF" $iobuf 94
        _xvr_subrow "BIBUF" $bibuf 95
        if {$ps7 > 0} { _xvr_row "PS7 (hard CPU)" $ps7 }

    } else {
    # --------------------------------------------------------------------------
    #  C O N C I S E   /   E X T R A   C O N C I S E   M O D E S
    # --------------------------------------------------------------------------
        _xvr_section "Resources"
        _xvr_col_hdr

        _xvr_rowseg "LUTs"         $lut_total $cap_lut    $lut_segs
        _xvr_rowseg "Flip-flops"   $ff_total  $cap_ff     $ff_segs
        _xvr_rowseg "SRLs"         $srl_total $cap_srl    $srl_segs
        _xvr_sep
        _xvr_row    "Carry chains" $carry
        _xvr_row    "MUXF7 / F8"  [expr {$muxf7 + $muxf8}]
        _xvr_sep
        _xvr_row    "DSP48"        $dsp       $cap_dsp
        _xvr_rowseg "BRAM (eq36)"  $bram_eq   $cap_bram36 $bram_segs
        _xvr_row    "Dist RAM"    [expr {$ram32m + $ram64m}]
        _xvr_sep
        _xvr_row    "BUFG / BUFR" [expr {$bufg + $bufr}]
        _xvr_row    "PLL / MMCM"  [expr {$pll  + $mmcm}]
        _xvr_rowseg "I/O Buffers"  $io_total  $cap_io     $io_segs
        if {$ps7 > 0} { _xvr_row "PS7 (hard CPU)" $ps7 }

        # Only print the legend in standard concise mode
        if {!$is_extra} {
            puts ""
            puts "  [_xvr_dim "Colour key:"]"
            puts [_xvr_legend $lut_legend  "    LUTs     "]
            puts [_xvr_legend $ff_legend   "    FFs      "]
            puts [_xvr_legend $bram_legend "    BRAMs    "]
            puts [_xvr_legend $srl_legend  "    SRLs     "]
            puts [_xvr_legend $io_legend   "    I/O      "]
        }

        if {$latch > 0} {
            puts ""
            puts "  [_xvr_yel "\u25b2  Warning: $latch inferred latch(es) \u2014 verify intent"]"
        }
    }


    # -- Timing (both modes) ---------------------------------------------------
    _xvr_section "Timing"
    if {[llength $clock_rows] == 0} {
        puts "  [_xvr_dim "(no timing data \u2014 pre-implementation)"]"
    } else {
        puts "[_xvr_dim "[format "  %-30s  %9s  %10s  %9s  %s" \
              Clock "Period ns" "Freq MHz" "WNS ns" "Fmax / Status"]"]"
        _xvr_sep
        foreach cd $clock_rows {
            lassign $cd cname period wns
            set freq_s [format "%.3f" [expr {1000.0 / $period}]]
            set line   [format "  %-32s  %6.3f ns  %8s MHz" $cname $period $freq_s]
            if {$wns ne ""} {
                set wns_s [format "%+.3f" $wns]
                if {$wns >= 0} {
                    set fmax_s [format "%.2f" [expr {1000.0 / ($period - $wns)}]]
                    append line "  [_xvr_grn $wns_s] ns  [_xvr_grn "\u2713 ${fmax_s} MHz"]"
                } else {
                    set need_s [format "%.2f" [expr {1000.0 / ($period - $wns)}]]
                    append line "  [_xvr_red $wns_s] ns  [_xvr_red "\u2717 FAILING (need ${need_s} MHz)"]"
                }
            } else {
                append line "  [_xvr_dim "n/a ns   ---"]"
            }
            puts $line
        }
    }


    # -- Placement & Summary ---------------------------------------------------
    # Skip entirely if we are in extra concise mode
    if {!$is_extra} {
        _xvr_section "Placement & Summary"
        set cr_str [join [lsort $cr_set] "  "]
        puts "  Clock regions used   [_xvr_bold $cr_count]   [_xvr_dim $cr_str]"
        puts "  LOC-fixed cells      [_xvr_bold $fixed_cnt]"
        puts "  Total primitives     [_xvr_bold $total_prims]"

        if {$is_detailed} {
            set ptype_str ""
            set line_w 0
            foreach r [lsort $ref_set] {
                if {$line_w + [string length $r] + 2 > 54} {
                    append ptype_str "\n[string repeat " " 25]"
                    set line_w 0
                }
                append ptype_str "  $r"
                incr line_w [expr {[string length $r] + 2}]
            }
            puts "  Primitive types ([llength $ref_set]):   [string trimleft $ptype_str]"
        } else {
            puts "  Primitive types      [_xvr_bold [llength $ref_set]]"
        }

        if {$bb_count > 0} {
            puts ""
            puts "  [_xvr_yel "\u25b2  $bb_count blackbox(es) in design:"]"
            foreach bb $blackboxes {
                puts "     [_xvr_dim "\u2022"] [get_property NAME $bb]"
            }
        }
    }

    puts ""
    puts "  \033\[1m[string repeat \u2550 [expr {$TW - 2}]]\033\[0m"
    puts ""
}