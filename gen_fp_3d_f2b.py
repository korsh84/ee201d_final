import sys, argparse, math
from parser import parse_info, parse_constraints
from gen_tsv_f2b import tsvTCL, TSVWIDTH, TSV2ioCellSpacingRatio, TSV2CoreBoxSpacingRatio


def main(args):
    botInfo = parse_info(args.design_info_bot)
    topInfo = parse_info(args.design_info_top)
    constraints = parse_constraints(args.tech_const)


    ################
    # for IO bumps #
    ################
    # give an pessimistic estimation of how many IO bumps are required per side
    # round up
    ioCellNumPerSide = botInfo['ioCount'] // 4
    if abs(botInfo['ioCount']/4.0 - ioCellNumPerSide) > 1e-6: ioCellNumPerSide += 1


    ################
    # for PG bumps #
    ################
    # want most compact area, calculate bump current with min area
    # this calculates the min bumps required to satisfy the power and current density constraints
    # bottom die needs to provide power to the top die
    currPerBump = constraints['bumpPitchSoC'] * constraints['bumpPitchSoC'] # um^2
    currPerBump = currPerBump * 1e-8 * constraints['currDen']               # um^2 to cm^2 to A
    targetCurr = (botInfo['designPower']+topInfo['designPower']) / 1.0      # VDD is 1.0,
    pgBumps = targetCurr // currPerBump + 1
    if pgBumps == 1: pgBumps += 1
    # 1:1 pgBumps
    pgBumps *= 2
    # find the smallest square value that is greater than pgBumps
    pgBumpsRow = math.sqrt(pgBumps)
    if abs(int(pgBumpsRow)-pgBumpsRow) > 1e-6: pgBumpsRow += 1
    pgBumpsRow = int(pgBumpsRow)
    pgBumpsCol = int(pgBumpsRow)
    #print ('pgBumps', pgBumps)


    ###############
    # for PG TSVs #
    ###############
    # these TSVs need to provide power to the top die
    currPerTSV = constraints['tsvPitchF2B'] * constraints['tsvPitchF2B'] # um^2
    currPerTSV = currPerTSV * 1e-8 * constraints['currDen']              # um^2 to cm^2 to A
    targetCurr = topInfo['designPower'] / 1.0                            # VDD is 1.0,
    pgTSVs = targetCurr // currPerTSV + 1
    if pgTSVs == 1: pgTSVs += 1
    # 1:1 pgTSVs
    pgTSVs *= 2
    #print ('pgTSVs', pgTSVs)


    #################
    # for floorplan #
    #################
    # 1. min area for min number of total bumps
    minTotalBumps = pgBumps + botInfo['ioCount']
    minSize4Bumps = math.sqrt(minTotalBumps)
    if abs(int(minSize4Bumps)-minSize4Bumps) > 1e-6: minSize4Bumps += 1
    minArea1 = minSize4Bumps**2
    # 2. find the core size which is the max of top and bot die
    botCoreArea = botInfo['designArea'] / botInfo['targetUtil']
    topCoreArea = topInfo['designArea'] / topInfo['targetUtil']
    targetCoreSize = math.ceil(math.sqrt(max(botCoreArea, topCoreArea)))
    # 3. min area for accounting for min number of tsv
    #    round core size to the min value that is greater than orgianl size and is a multiple of tsv pitch
    tmp = (targetCoreSize // constraints['tsvPitchF2B']) * constraints['tsvPitchF2B']
    targetCoreSize = tmp+constraints['tsvPitchF2B'] if tmp < targetCoreSize else tmp
    targetTSVPlaceStartSize = targetCoreSize + 2*(TSV2ioCellSpacingRatio*constraints['tsvPitchF2B'])
    totalTSVs = botInfo['tsvCount'] + pgTSVs
    poolTSVs = int(totalTSVs)
    nRings4TSV = 0
    while poolTSVs > 0:
        poolTSVs -= (4*(targetTSVPlaceStartSize//constraints['tsvPitchF2B']) - 4)
        targetTSVPlaceStartSize += 2*constraints['tsvPitchF2B']
        nRings4TSV += 1
    minArea2 = (targetTSVPlaceStartSize+2*(TSV2ioCellSpacingRatio*constraints['tsvPitchF2B'])+2*constraints['ioCellHeight'])**2
    # 4. adjust spacing
    if minArea1 > minArea2:
        spacing = minSize4Bumps - targetCoreSize
    else:
        # final spacing to fit IO cells and tsv
        spacing = constraints['tsvPitchF2B']*(nRings4TSV-1) + constraints['tsvPitchF2B']*(TSV2ioCellSpacingRatio+TSV2CoreBoxSpacingRatio) + TSVWIDTH
    print (targetCoreSize)
    print (nRings4TSV)
    print (spacing)
    # 5. final floorplan dimension
    coreDim = round(targetCoreSize)


    ####################
    # final tcl script #
    ####################
    fp_tcl_bot = '''\
#############
# floorPlan #
#############
floorPlan -site FreePDK45_38x28_10R_NP_162NW_34O -s {0} {0} {1} {1} {1} {1}


##############
# Place TSVs #
##############
source "scripts_own/riscv_core_tsv_f2b.tcl"


#############
# for bumps #
#############
set ioCellNumX {2}
set ioCellNumY {2}
set ioBumpBudgetX [expr [dbGet top.fPlan.box_sizex]-2.1*{3}]
set ioBumpBudgetY [expr [dbGet top.fPlan.box_sizey]-2.1*{3}]
set ioBumpPitchX [max {4} [expr $ioBumpBudgetX / [expr $ioCellNumX-1.0]]]
set ioBumpPitchY [max {4} [expr $ioBumpBudgetY / [expr $ioCellNumY-1.0]]]

# recalculate pitch so that bumps distribute evenly
set ioBumpPitchX [expr $ioBumpBudgetX / [expr floor($ioBumpBudgetX / $ioBumpPitchX)]]
set ioBumpPitchY [expr $ioBumpBudgetY / [expr floor($ioBumpBudgetY / $ioBumpPitchY)]]

# create bumps, distribute evenly accross entire die
set ioMarginX {3}
set ioMarginY {3}
create_bump -cell BUMPCELL -pitch [list [expr $ioBumpPitchX] [expr $ioBumpPitchY]] -pattern_side [list left [expr $ioBumpBudgetX / $ioBumpPitchX + 1]] \\
            -edge_spacing [list [expr $ioMarginX] [expr $ioMarginY] [expr $ioMarginX] [expr $ioMarginY]]

# assign IO bumps
# the remaining floating bumps are guaranteed to be sufficient for pgBumps since the area is already pre-calculated
assignBump
assignPGBumps -nets {{VDD VSS}} -floating -V


##########################################
# RDL Routing between IO cells and bumps #
##########################################
setFlipChipMode -route_style 45DegreeRoute
fcroute -type signal -designStyle pio -layerChangeBotLayer metal7 -layerChangeTopLayer metal10 -routeWidth 0
'''.format(coreDim,
           spacing,
           ioCellNumPerSide,
           constraints['ioCellHeight'],
           constraints['bumpPitchSoC'])

    fp_tcl_top = '''\
#############
# floorPlan #
#############
floorPlan -site FreePDK45_38x28_10R_NP_162NW_34O -s {0} {0} {1} {1} {1} {1}

##############
# Place TSVs #
##############
source "scripts_own/riscv_core_tsv_f2b.tcl"

##############
# for ubumps #
##############
source "scripts_own/riscv_core_ubump_f2b.tcl"
assignPGBumps -nets {{VDD}} -bumps {{pubump*}}
assignPGBumps -nets {{VSS}} -bumps {{gubump*}}
assignBump

##########################################
# RDL Routing between IO cells and bumps #
##########################################
setFlipChipMode -route_style 45DegreeRoute
fcroute -type signal -designStyle pio -layerChangeBotLayer metal7 -layerChangeTopLayer metal10 -routeWidth 0
'''.format(coreDim,
           spacing)

    ##################
    # Gen TSV script #
    ##################
    # 1. parse in all required TSVs
    # 2. collect them into a set and gen placement script statically
    tsvTcl, uBumpTcl = tsvTCL(args.design_netlist, constraints['tsvPitchF2B'], constraints['ioCellHeight'], coreDim, spacing, int(pgTSVs), f2b=True)
    with open('riscv_core_tsv_f2b.tcl', 'w') as f:
        f.write(tsvTcl)
    with open('riscv_core_ubump_f2b.tcl', 'w') as f:
        f.write(uBumpTcl)

    return fp_tcl_bot, fp_tcl_top


def parse():
    parser = argparse.ArgumentParser()
    parser.add_argument('--design-info-bot', required=True, type=str)
    parser.add_argument('--design-info-top', required=True, type=str)
    parser.add_argument('--design-netlist', required=True, type=str)
    parser.add_argument('--tech-const', required=True, type=str)
    return parser.parse_args()

if __name__ == '__main__':
    bot, top = main(parse())
    with open('fp_3d_f2b_bottom.tcl', 'w') as f:
        f.write(bot)
    with open('fp_3d_f2b_top.tcl', 'w') as f:
        f.write(top)
