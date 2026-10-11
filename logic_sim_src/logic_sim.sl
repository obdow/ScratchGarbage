# Logic Sim - a digital logic simulator for the Scratch pen layer.
# Compiled to Scratch blocks by slc.py (see build.py). Text is drawn with the
# Pen Text Engine custom blocks that live in the same sprite.

extern drawtext = "draw text %s at x: %s y: %s"
extern drawtextw = "draw text %s at x: %s y: %s wrap width: %s"
extern measuretext = "measure text %s wrap width: %s"
extern tsize = "set text size to %s"
extern talign = "set text align %s vertical %s"
extern tcolor = "set text color hue: %s brightness: %s"
extern ttrans = "set text transparency to %s"
extern treset = "reset text style"
global `TE width`, `TE height`, `Circuit code`

# ---- part types (order = palette order)
const T_AND = 1
const T_OR = 2
const T_NOT = 3
const T_NAND = 4
const T_NOR = 5
const T_XOR = 6
const T_XNOR = 7
const T_BUF = 8
const T_SWITCH = 9
const T_BUTTON = 10
const T_CLOCK = 11
const T_CONST = 12
const T_LED = 13
const T_HEX = 14
const T_SEG7 = 15
const T_DFF = 16
const T_DEC7 = 17
const T_LABEL = 18
const T_TABLE = 19
const T_NUM = 20
const NT = 20

# ---- colours
const C_GRID = 0x151c25
const C_GRID2 = 0x1b2430
const C_HIGH = 0x3dff8a
const C_LOW = 0x3a4b5c
const C_GLOW = 0x553dff8a
const C_WHOV = 0xb8ffd4
const C_LOWHOV = 0x7d93a8
const C_PANEL = 0x10161e
const C_PANEL2 = 0x18212c
const C_BTN = 0x212c39
const C_BTNH = 0x2f3e50
const C_ACCENT = 0x2fd477
const C_EDGE = 0x2a3644
const C_ROW = 0x23382b

# ---- baked tables (filled in by build.py)
list tp_name, tp_desc, tp_hint, tp_nin, tp_nout, tp_pin0, pin_dx, pin_dy
list tp_hw, tp_hh, tp_op0, tp_opn, op_k, op_a, op_b, op_c, op_d, op_e
list tp_tx0, tp_txn, tx_s, tx_x, tx_y, tx_sz, tx_al
list tp_ics, tp_icx, tp_icy, tp_lpos, tp_defstate, tp_defparam
list segtab, led_on, led_off, led_glow, speeds, speedname
list btn_x1, btn_x2, btn_y1, btn_y2, btn_label, btn_tip, btn_bg
list demo_name, demo_desc, demo_code, demo_speed, demo_info, help_lines

# ---- circuit state
list c_type, c_x, c_y, c_in0, c_out0, c_state, c_aux, c_param, c_label, c_w
list in_src, in_comp, in_x, in_y, in_mid
list outv, outn, out_comp, out_x, out_y
list rpx, rpy, recs, flds, cmap, keyq

var ncomp, camx, camy, zoom, running, speed, acc, ticks, stepreq
var mx, my, md, pmd, wx, wy, drag, dc, dox, doy, dsx, dsy, wfrom, wkind, dw, pax, pay, isnew
var hovb, hovp, hovpin, hovpk, hovc, hovw, hovws, hovwm, zone, hint
var lm, help, showinfo, demo, infoh, infotop, exporting, pend, pendc, msg, msgt, segs
# temporaries (each prefix belongs to one procedure)
var tc, tt, ti, to, ta, tb, tn, tsg, tj, ty, tk
var ak, dk, dvis, cc, cv, lp, qx, qy, qm, gk, gs, gx, gsx
var rs, rx1, ry1, rx2, ry2, rm, rmid, rfwd, wk, wj, wv, wr, wax, way, wbx, wby, wlo, whi
var pk, pr, pbest, pd, hk, hw2, hh2, hb, hrow
var ct, ck, cw, ttxt, sj, rch, spi, sptok, spch, sani
var ek, en, es, esv, ed, esc, ik, iok, idc, isc
var ux, uy, ui, ub, ulab, uh, ut, ux1, ux2, uy1, uy2, uyy
var fl, bx1, bx2, by1, by2, fhw, fhh, fz, fk, nz, zwx, zwy
var lt0, lt1, ldx, ldy, lok, lr, dlk, dlo, dli, dln

## LOGIC SIM - main loop. Everything is redrawn on the pen layer each frame.
## Data model: parallel lists. c_* = parts, in_* = input pins (in_src = the
## output slot that drives it, 1 = unconnected/ground), out_* = output pins.
## Every part has one tick of delay: outputs are computed into outn, then
## copied into outv, so feedback loops (latches, oscillators) just work.
when flag
  init()
  forever
    frame()
  end
end

when key "space"
  keyq.add("space")
end
when key "s"
  keyq.add("s")
end
when key "x"
  keyq.add("x")
end
when key "l"
  keyq.add("l")
end
when key "f"
  keyq.add("f")
end
when key "h"
  keyq.add("h")
end
when key "i"
  keyq.add("i")
end
when key "up arrow"
  keyq.add("up")
end
when key "down arrow"
  keyq.add("down")
end
when key "="
  keyq.add("up")
end
when key "-"
  keyq.add("down")
end
when key "left arrow"
  keyq.add("left")
end
when key "right arrow"
  keyq.add("right")
end

def init()
  hide()
  treset()
  zoom = 1
  camx = 0
  camy = 0
  running = 1
  speed = 4
  acc = 0
  drag = 0
  pmd = 0
  help = 0
  exporting = 0
  pend = 0
  msgt = 0
  stepreq = 0
  keyq.clear()
  `Circuit code`.hide()
  loaddemo(1)
end

def frame()
  if pend > 0
    dopending()
  end
  readinput()
  dokeys()
  if drag == 0
    hover()
  end
  mouse()
  simulate()
  render()
  pmd = md
end

def readinput()
  mx = mousex()
  my = mousey()
  if mousedown()
    md = 1
  else
    md = 0
  end
  wx = mx / zoom + camx
  wy = my / zoom + camy
end

def snapv(v)
  sj = round(v / 10) * 10
end

# ------------------------------------------------------------------ circuit

def clearall()
  c_type.clear()
  c_x.clear()
  c_y.clear()
  c_in0.clear()
  c_out0.clear()
  c_state.clear()
  c_aux.clear()
  c_param.clear()
  c_label.clear()
  c_w.clear()
  in_src.clear()
  in_comp.clear()
  in_x.clear()
  in_y.clear()
  in_mid.clear()
  outv.clear()
  outn.clear()
  out_comp.clear()
  out_x.clear()
  out_y.clear()
  # output slot 1 is "ground": a constant 0 that unconnected inputs read
  outv.add(0)
  outn.add(0)
  out_comp.add(0)
  out_x.add(0)
  out_y.add(0)
  ncomp = 0
  ticks = 0
  hovc = 0
  hovw = 0
  hovpin = 0
end

def addcomp(t, x, y)
  c_type.add(t)
  c_x.add(x)
  c_y.add(y)
  c_in0.add(count(in_src) + 1)
  c_out0.add(count(outv) + 1)
  c_state.add(tp_defstate[t])
  c_aux.add(0)
  c_param.add(tp_defparam[t])
  c_label.add("")
  c_w.add(0)
  ncomp = count(c_type)
  ak = tp_pin0[t]
  repeat tp_nin[t]
    in_src.add(1)
    in_comp.add(ncomp)
    in_x.add(x + pin_dx[ak])
    in_y.add(y + pin_dy[ak])
    in_mid.add("")
    ak += 1
  end
  repeat tp_nout[t]
    outv.add(0)
    outn.add(0)
    out_comp.add(ncomp)
    out_x.add(x + pin_dx[ak])
    out_y.add(y + pin_dy[ak])
    ak += 1
  end
  initout(ncomp)
end

# set a part's outputs from its state, so loaded circuits start consistent
def initout(c)
  ak = c_out0[c]
  if c_type[c] < 13
    outv[ak] = c_state[c]
    outn[ak] = c_state[c]
  elif c_type[c] == T_DFF
    outv[ak] = c_state[c]
    outn[ak] = c_state[c]
    outv[ak + 1] = 1 - c_state[c]
    outn[ak + 1] = 1 - c_state[c]
    # ignore a "rising edge" caused by parts upstream powering up
    c_aux[c] = 1
  end
end

def setpins(c)
  ak = tp_pin0[c_type[c]]
  pk = c_in0[c]
  repeat tp_nin[c_type[c]]
    in_x[pk] = c_x[c] + pin_dx[ak]
    in_y[pk] = c_y[c] + pin_dy[ak]
    ak += 1
    pk += 1
  end
  pk = c_out0[c]
  repeat tp_nout[c_type[c]]
    out_x[pk] = c_x[c] + pin_dx[ak]
    out_y[pk] = c_y[c] + pin_dy[ak]
    ak += 1
    pk += 1
  end
end

def delcomp(c)
  dlo = c_out0[c]
  dln = tp_nout[c_type[c]]
  dlk = 1
  repeat count(in_src)
    if in_src[dlk] >= dlo and in_src[dlk] < dlo + dln
      in_src[dlk] = 1
      in_mid[dlk] = ""
    end
    dlk += 1
  end
  dli = c_in0[c]
  repeat tp_nin[c_type[c]]
    in_src[dli] = 1
    in_comp[dli] = 0
    dli += 1
  end
  dli = dlo
  repeat dln
    out_comp[dli] = 0
    outv[dli] = 0
    outn[dli] = 0
    dli += 1
  end
  c_type[c] = 0
  c_label[c] = ""
  if hovc == c
    hovc = 0
  end
end

# wires attached to a part that moved go back to automatic routing
def clearmids(c)
  dlo = c_out0[c]
  dln = tp_nout[c_type[c]]
  dlk = 1
  repeat count(in_src)
    if in_comp[dlk] == c or (in_src[dlk] >= dlo and in_src[dlk] < dlo + dln)
      in_mid[dlk] = ""
    end
    dlk += 1
  end
end

def setlabel(c, s)
  c_label[c] = s
  if c_type[c] == T_LABEL
    tsize(c_param[c])
    measuretext(s, 0)
    c_w[c] = `TE width` / 2 + 3
    lm = 0
  end
end

# replace character i of s with ch -> rch
def setchar(s, i, ch)
  rch = ""
  sj = 1
  repeat strlen(s)
    if sj == i
      rch = join(rch, ch)
    else
      rch = join(rch, letter(sj, s))
    end
    sj += 1
  end
end

# ------------------------------------------------------------------ simulation

def simulate()
  if running == 1
    acc += speeds[speed]
    if acc > 64
      acc = 64
    end
    while acc >= 1
      tick()
      acc -= 1
    end
  end
  repeat stepreq
    tick()
  end
  stepreq = 0
end

## One simulation tick: every part reads its inputs from outv (last tick's
## values) and writes new outputs to outn; then outn is copied to outv.
def tick()
  tc = 1
  repeat ncomp
    tt = c_type[tc]
    if tt > 0
      ti = c_in0[tc]
      to = c_out0[tc]
      if tt < 9
        ta = outv[in_src[ti]]
        if tt == T_NOT
          outn[to] = 1 - ta
        elif tt == T_BUF
          outn[to] = ta
        else
          tb = outv[in_src[ti + 1]]
          if tt == T_AND
            outn[to] = ta * tb
          elif tt == T_OR
            outn[to] = ta + tb - ta * tb
          elif tt == T_NAND
            outn[to] = 1 - ta * tb
          elif tt == T_NOR
            outn[to] = (1 - ta) * (1 - tb)
          elif tt == T_XOR
            outn[to] = (ta + tb) % 2
          else
            outn[to] = 1 - (ta + tb) % 2
          end
        end
      elif tt < 13
        if tt == T_CLOCK
          c_aux[tc] = c_aux[tc] + 1
          if c_aux[tc] >= c_param[tc]
            c_aux[tc] = 0
            c_state[tc] = 1 - c_state[tc]
          end
        end
        outn[to] = c_state[tc]
      elif tt == T_DFF
        tb = outv[in_src[ti + 1]]
        if tb == 1 and c_aux[tc] == 0
          c_state[tc] = outv[in_src[ti]]
        end
        c_aux[tc] = tb
        outn[to] = c_state[tc]
        outn[to + 1] = 1 - c_state[tc]
      elif tt == T_DEC7
        tn = outv[in_src[ti]] + 2 * outv[in_src[ti + 1]] + 4 * outv[in_src[ti + 2]] + 8 * outv[in_src[ti + 3]]
        tsg = segtab[tn + 1]
        tj = 1
        repeat 7
          outn[to + tj - 1] = letter(tj, tsg)
          tj += 1
        end
      elif tt == T_TABLE
        if in_src[ti + 2] > 1
          ta = outv[in_src[ti]]
          if in_src[ti + 1] > 1
            tb = outv[in_src[ti + 1]]
          else
            tb = 0
          end
          tn = 2 * ta + tb + 1
          ty = outv[in_src[ti + 2]]
          if letter(tn, c_state[tc]) != ty
            setchar(c_state[tc], tn, ty)
            c_state[tc] = rch
          end
        end
      end
    end
    tc += 1
  end
  tk = 2
  repeat count(outv) - 1
    outv[tk] = outn[tk]
    tk += 1
  end
  ticks += 1
end

# ------------------------------------------------------------------ input

def dokeys()
  repeat count(keyq)
    dokey(keyq[1])
    keyq.del(1)
  end
end

def dokey(k)
  if pend > 0
    return
  end
  if k == "space"
    running = 1 - running
  elif k == "s"
    running = 0
    stepreq += 1
  elif k == "up"
    zoomkey(1.2)
  elif k == "down"
    zoomkey(1 / 1.2)
  elif k == "left"
    loaddemo(demo - 1)
  elif k == "right"
    loaddemo(demo + 1)
  elif k == "x"
    if drag == 0
      if hovc > 0
        delcomp(hovc)
      elif hovw > 0
        in_src[hovw] = 1
        in_mid[hovw] = ""
        hovw = 0
      end
    end
  elif k == "l"
    if hovc > 0 and drag == 0
      pend = 1
      pendc = hovc
    end
  elif k == "f"
    fitview()
  elif k == "h"
    help = 1 - help
  elif k == "i"
    toggleinfo()
  end
end

def zoomkey(f)
  if zone == 5
    zoomby(f, mx, my)
  else
    zoomby(f, 28, -14)
  end
end

def zoomby(f, ax, ay)
  nz = zoom * f
  if nz < 0.25
    nz = 0.25
  end
  if nz > 4
    nz = 4
  end
  zwx = ax / zoom + camx
  zwy = ay / zoom + camy
  camx = zwx - ax / nz
  camy = zwy - ay / nz
  zoom = nz
end

def toggleinfo()
  if demo > 0
    showinfo = 1 - showinfo
  end
end

## Hover: figure out what is under the mouse (toolbar button, palette item,
## pin, part or wire) and the hint for the status bar.
def hover()
  hovb = 0
  hovp = 0
  hovpin = 0
  hovpk = 0
  hovc = 0
  hovw = 0
  zone = 0
  hint = ""
  if help == 1 or exporting == 1
    zone = 9
    return
  end
  hb = 1
  repeat count(btn_x1)
    if mx >= btn_x1[hb] and mx <= btn_x2[hb] and my >= btn_y1[hb] and my <= btn_y2[hb]
      hovb = hb
    end
    hb += 1
  end
  if hovb > 0
    zone = 1
    hint = btn_tip[hovb]
    return
  end
  if my > 152
    zone = 1
    return
  end
  if mx < -184
    zone = 2
    hrow = floor((153 - my) / 26)
    if hrow >= 0 and hrow < NT / 2
      hovp = hrow * 2 + 1
      if mx > -212
        hovp += 1
      end
      hint = "Drag onto the board to add this part"
    end
    return
  end
  if showinfo == 1 and demo > 0 and my < infotop and my > -165 and mx > -182
    zone = 3
    hint = "Click to hide this panel (I shows it again)"
    return
  end
  if my < -165
    zone = 4
    return
  end
  zone = 5
  pinhit(0)
  if hovpin > 0
    if hovpk == 1
      hint = "Output pin: drag to an input pin to connect a wire"
    elif in_src[hovpin] > 1
      hint = "Input pin: drag the wire end away to disconnect or move it"
    else
      hint = "Input pin: drag to an output pin to connect a wire"
    end
    return
  end
  comphit()
  if hovc > 0
    hint = tp_hint[c_type[hovc]]
    return
  end
  wirehit()
  if hovw > 0
    if hovwm == 1
      hint = "Wire: drag to re-route  |  X deletes it"
    else
      hint = "Wire: X deletes it  |  drag its middle segment to re-route"
    end
    return
  end
  hint = "Drag to pan  |  scroll or Up/Down to zoom  |  H for help"
end

# want: 0 = any pin, 1 = outputs only, 2 = inputs only
def pinhit(want)
  hovpin = 0
  hovpk = 0
  pr = 8 / zoom
  if pr > 12
    pr = 12
  end
  pbest = pr * pr
  if want != 1
    pk = 1
    repeat count(in_x)
      if in_comp[pk] > 0
        pd = (in_x[pk] - wx) * (in_x[pk] - wx) + (in_y[pk] - wy) * (in_y[pk] - wy)
        if pd < pbest
          pbest = pd
          hovpin = pk
          hovpk = 2
        end
      end
      pk += 1
    end
  end
  if want != 2
    pk = 2
    repeat count(out_x) - 1
      if out_comp[pk] > 0
        pd = (out_x[pk] - wx) * (out_x[pk] - wx) + (out_y[pk] - wy) * (out_y[pk] - wy)
        if pd < pbest
          pbest = pd
          hovpin = pk
          hovpk = 1
        end
      end
      pk += 1
    end
  end
end

def comphit()
  hk = ncomp
  until hk < 1 or hovc > 0
    if c_type[hk] > 0
      if c_type[hk] == T_LABEL
        hw2 = c_w[hk]
        hh2 = c_param[hk] * 0.6
      else
        hw2 = tp_hw[c_type[hk]]
        hh2 = tp_hh[c_type[hk]]
      end
      if abs(wx - c_x[hk]) <= hw2 + 2 and abs(wy - c_y[hk]) <= hh2 + 2
        hovc = hk
      end
    end
    hk -= 1
  end
end

## Wires are routed orthogonally from the output pin to the input pin.
## Forward wires bend at x = in_mid (default: halfway); wires going
## backwards loop around at y = in_mid. Points go into rpx / rpy.
def route(k)
  rs = in_src[k]
  rx1 = out_x[rs]
  ry1 = out_y[rs]
  rx2 = in_x[k]
  ry2 = in_y[k]
  rpx.clear()
  rpy.clear()
  rpx.add(rx1)
  rpy.add(ry1)
  rmid = 0
  if rx2 >= rx1 + 10
    rfwd = 1
    if ry1 != ry2
      rm = in_mid[k]
      if rm == ""
        rm = round((rx1 + rx2) / 20) * 10
      end
      if rm < rx1 + 5
        rm = rx1 + 5
      end
      if rm > rx2 - 5
        rm = rx2 - 5
      end
      rpx.add(rm)
      rpy.add(ry1)
      rpx.add(rm)
      rpy.add(ry2)
      rmid = 2
    end
  else
    rfwd = 0
    rm = in_mid[k]
    if rm == ""
      if ry1 < ry2
        rm = ry1 - 30
      else
        rm = ry2 - 30
      end
    end
    rpx.add(rx1 + 10)
    rpy.add(ry1)
    rpx.add(rx1 + 10)
    rpy.add(rm)
    rpx.add(rx2 - 10)
    rpy.add(rm)
    rpx.add(rx2 - 10)
    rpy.add(ry2)
    rmid = 3
  end
  rpx.add(rx2)
  rpy.add(ry2)
end

def wirehit()
  wr = 5 / zoom
  wk = 1
  until wk > count(in_src) or hovw > 0
    if in_comp[wk] > 0 and in_src[wk] > 1
      route(wk)
      wj = 1
      until wj >= count(rpx) or hovw > 0
        wax = rpx[wj]
        way = rpy[wj]
        wbx = rpx[wj + 1]
        wby = rpy[wj + 1]
        if way == wby
          if wax < wbx
            wlo = wax
            whi = wbx
          else
            wlo = wbx
            whi = wax
          end
          if abs(wy - way) < wr and wx > wlo - wr and wx < whi + wr
            hovw = wk
          end
        else
          if way < wby
            wlo = way
            whi = wby
          else
            wlo = wby
            whi = way
          end
          if abs(wx - wax) < wr and wy > wlo - wr and wy < whi + wr
            hovw = wk
          end
        end
        if hovw > 0
          hovws = wj
          if wj == rmid
            hovwm = 1
          else
            hovwm = 0
          end
        end
        wj += 1
      end
    end
    wk += 1
  end
end

def mouse()
  if md == 1 and pmd == 0
    press()
  elif md == 1
    held()
  elif pmd == 1
    release()
  end
end

def press()
  if exporting == 1
    exporting = 0
    `Circuit code`.hide()
    return
  end
  if help == 1
    help = 0
    return
  end
  if pend > 0
    return
  end
  if hovb > 0
    button(hovb)
    return
  end
  if zone == 2
    if hovp > 0
      newpart(hovp)
    end
    return
  end
  if zone == 3
    showinfo = 0
    return
  end
  if zone != 5
    return
  end
  dsx = mx
  dsy = my
  if hovpin > 0
    drag = 3
    if hovpk == 1
      wfrom = hovpin
      wkind = 1
    elif in_src[hovpin] > 1
      # pick up the end of an existing wire
      wfrom = in_src[hovpin]
      in_src[hovpin] = 1
      in_mid[hovpin] = ""
      wkind = 1
    else
      wfrom = hovpin
      wkind = 2
    end
    return
  end
  if hovc > 0
    drag = 4
    dc = hovc
    dox = c_x[dc] - wx
    doy = c_y[dc] - wy
    if c_type[dc] == T_BUTTON
      c_state[dc] = 1
    end
    return
  end
  if hovw > 0 and hovwm == 1
    drag = 5
    dw = hovw
    return
  end
  drag = 1
  pax = wx
  pay = wy
end

def held()
  if drag == 1
    camx = pax - mx / zoom
    camy = pay - my / zoom
  elif drag == 4
    if abs(mx - dsx) + abs(my - dsy) > 4
      drag = 2
      if c_type[dc] == T_BUTTON
        c_state[dc] = 0
      end
    end
  elif drag == 3
    if wkind == 1
      pinhit(2)
    else
      pinhit(1)
    end
  elif drag == 5
    route(dw)
    if rfwd == 1
      snapv(wx)
    else
      snapv(wy)
    end
    in_mid[dw] = sj
  end
  if drag == 2
    snapv(wx + dox)
    ux = sj
    snapv(wy + doy)
    if ux != c_x[dc] or sj != c_y[dc]
      c_x[dc] = ux
      c_y[dc] = sj
      setpins(dc)
    end
  end
end

def release()
  if drag == 2
    if mx < -184 or my > 152
      delcomp(dc)
    else
      clearmids(dc)
      if isnew == 1 and c_type[dc] == T_LABEL
        pend = 1
        pendc = dc
      end
    end
  elif drag == 4
    click(dc)
  elif drag == 3
    if hovpin > 0
      if wkind == 1 and hovpk == 2
        in_src[hovpin] = wfrom
        in_mid[hovpin] = ""
      elif wkind == 2 and hovpk == 1
        in_src[wfrom] = hovpin
        in_mid[wfrom] = ""
      end
    end
  end
  drag = 0
  isnew = 0
end

def click(c)
  ct = c_type[c]
  if ct == T_SWITCH or ct == T_CONST
    c_state[c] = 1 - c_state[c]
  elif ct == T_BUTTON
    c_state[c] = 0
  elif ct == T_CLOCK
    c_param[c] = c_param[c] * 2
    if c_param[c] > 32
      c_param[c] = 2
    end
    c_aux[c] = 0
  elif ct == T_LED
    c_param[c] = c_param[c] + 1
    if c_param[c] > count(led_on)
      c_param[c] = 1
    end
  elif ct == T_LABEL
    pend = 1
    pendc = c
  elif ct == T_TABLE
    c_state[c] = "????"
  end
end

def newpart(t)
  snapv(wx)
  ux = sj
  snapv(wy)
  addcomp(t, ux, sj)
  dc = ncomp
  if t == T_LABEL
    setlabel(dc, "Label")
  end
  drag = 2
  dox = 0
  doy = 0
  isnew = 1
end

def button(b)
  if b == 1
    running = 1 - running
  elif b == 2
    running = 0
    stepreq += 1
  elif b == 3
    if speed > 1
      speed -= 1
    end
  elif b == 4
    if speed < count(speeds)
      speed += 1
    end
  elif b == 5
    loaddemo(demo - 1)
  elif b == 6
    loaddemo(demo + 1)
  elif b == 7
    clearall()
    demo = 0
    showinfo = 0
    zoom = 1
    camx = -28
    camy = 14
    running = 1
    msg = "New empty board - drag parts in from the palette"
    msgt = 150
  elif b == 8
    export()
  elif b == 9
    pend = 2
  elif b == 10
    help = 1
  elif b == 11
    zoomby(1.25, 28, -14)
  elif b == 12
    zoomby(0.8, 28, -14)
  elif b == 13
    fitview()
  elif b == 14
    toggleinfo()
  end
end

# questions are asked at the start of a frame, so the last frame stays visible
def dopending()
  if pend == 1
    if c_type[pendc] == T_LABEL
      ask("Text for this label:")
    else
      ask(join("Label for this ", join(tp_name[c_type[pendc]], " (leave blank for none):")))
    end
    sanitize(answer())
    if c_type[pendc] == T_LABEL and sani == ""
      delcomp(pendc)
    else
      setlabel(pendc, sani)
    end
  elif pend == 2
    ask("Paste a circuit code and press Enter (blank cancels):")
    if answer() != ""
      importcode(answer())
      if iok == 1
        demo = 0
        showinfo = 0
        fitview()
        msg = "Circuit loaded"
        msgt = 120
      end
    end
  end
  pend = 0
  # the mouse button was released while the question was open
  pmd = 0
  drag = 0
end

# remove the characters used by the save format
def sanitize(s)
  sani = ""
  sj = 1
  repeat strlen(s)
    if letter(sj, s) == ";" or letter(sj, s) == ","
      sani = join(sani, " ")
    else
      sani = join(sani, letter(sj, s))
    end
    sj += 1
  end
end

# ------------------------------------------------------------------ view

def fitview()
  if ncomp == 0
    zoom = 1
    camx = -28
    camy = 14
    return
  end
  bx1 = 1000000
  bx2 = -1000000
  by1 = 1000000
  by2 = -1000000
  fk = 1
  repeat ncomp
    if c_type[fk] > 0
      if c_type[fk] == T_LABEL
        fhw = c_w[fk]
        fhh = c_param[fk] * 0.6
        fl = 0
      else
        fhw = tp_hw[c_type[fk]] + 12
        fhh = tp_hh[c_type[fk]] + 4
        fl = 0
        if c_label[fk] != ""
          fl = tp_lpos[c_type[fk]]
        end
      end
      # labels stick out to the left, right or top of a part
      ux = fhw
      if fl == 1
        ux = fhw + strlen(c_label[fk]) * 6 + 4
      end
      if c_x[fk] - ux < bx1
        bx1 = c_x[fk] - ux
      end
      ux = fhw
      if fl == 2
        ux = fhw + strlen(c_label[fk]) * 6 + 4
      end
      if c_x[fk] + ux > bx2
        bx2 = c_x[fk] + ux
      end
      if c_y[fk] - fhh < by1
        by1 = c_y[fk] - fhh
      end
      ux = fhh
      if fl == 3
        ux = fhh + 14
      end
      if c_y[fk] + ux > by2
        by2 = c_y[fk] + ux
      end
    end
    fk += 1
  end
  # screen area to fit into
  ux1 = -176
  ux2 = 232
  uy1 = -160
  uy2 = 144
  if showinfo == 1 and demo > 0
    uy1 = infotop + 6
  end
  zoom = (ux2 - ux1) / (bx2 - bx1)
  fz = (uy2 - uy1) / (by2 - by1)
  if fz < zoom
    zoom = fz
  end
  if zoom > 2
    zoom = 2
  end
  if zoom < 0.25
    zoom = 0.25
  end
  camx = (bx1 + bx2) / 2 - ((ux1 + ux2) / 2) / zoom
  camy = (by1 + by2) / 2 - ((uy1 + uy2) / 2) / zoom
end

def loaddemo(n)
  demo = n
  if demo < 1
    demo = count(demo_name)
  end
  if demo > count(demo_name)
    demo = 1
  end
  importcode(demo_code[demo])
  speed = demo_speed[demo]
  running = 1
  acc = 0
  showinfo = demo_info[demo]
  tsize(10)
  measuretext(demo_desc[demo], 396)
  infoh = `TE height` + 34
  infotop = -165 + infoh
  lm = 0
  fitview()
end

# ------------------------------------------------------------------ save / load

def export()
  cmap.clear()
  en = 0
  ek = 1
  repeat ncomp
    if c_type[ek] > 0
      en += 1
      cmap.add(en)
    else
      cmap.add(0)
    end
    ek += 1
  end
  es = "LS1"
  ek = 1
  repeat ncomp
    if c_type[ek] > 0
      # gates save their current output so latches keep their state
      if c_type[ek] < 9
        esv = outv[c_out0[ek]]
      else
        esv = c_state[ek]
      end
      es = join(es, ";P,", c_type[ek], ",", c_x[ek], ",", c_y[ek], ",", esv, ",", c_param[ek], ",", c_label[ek])
    end
    ek += 1
  end
  ek = 1
  repeat count(in_src)
    if in_comp[ek] > 0 and in_src[ek] > 1
      ed = in_comp[ek]
      esc = out_comp[in_src[ek]]
      es = join(es, ";W,", cmap[ed], ",", ek - c_in0[ed], ",", cmap[esc], ",", in_src[ek] - c_out0[esc], ",", in_mid[ek])
    end
    ek += 1
  end
  `Circuit code`.clear()
  `Circuit code`.add(es)
  `Circuit code`.show()
  exporting = 1
end

def splitrecs(s)
  recs.clear()
  sptok = ""
  spi = 1
  repeat strlen(s)
    spch = letter(spi, s)
    if spch == ";"
      recs.add(sptok)
      sptok = ""
    else
      sptok = join(sptok, spch)
    end
    spi += 1
  end
  recs.add(sptok)
end

def splitflds(s)
  flds.clear()
  sptok = ""
  spi = 1
  repeat strlen(s)
    spch = letter(spi, s)
    if spch == ","
      flds.add(sptok)
      sptok = ""
    else
      sptok = join(sptok, spch)
    end
    spi += 1
  end
  flds.add(sptok)
end

def importcode(s)
  iok = 0
  splitrecs(s)
  if recs[1] != "LS1"
    msg = "That is not a circuit code (it should start with LS1)"
    msgt = 180
    return
  end
  clearall()
  ik = 2
  repeat count(recs) - 1
    splitflds(recs[ik])
    if flds[1] == "P"
      addcomp(flds[2], flds[3], flds[4])
      c_state[ncomp] = flds[5]
      initout(ncomp)
      c_param[ncomp] = flds[6]
      setlabel(ncomp, flds[7])
    elif flds[1] == "W"
      idc = c_in0[flds[2]] + flds[3]
      in_src[idc] = c_out0[flds[4]] + flds[5]
      in_mid[idc] = flds[6]
    end
    ik += 1
  end
  iok = 1
end

# ------------------------------------------------------------------ drawing primitives

def linemode()
  # the 4000px empty '_fence' costume at 100% lets the sprite move far off
  # stage without Scratch's fencing pulling it back
  costume("_size large")
  setsize(100)
  costume("_fence")
  lm = 1
end

def ln(x1, y1, x2, y2)
  if lm == 0
    linemode()
  end
  if x1 < -330 and x2 < -330
    return
  end
  if x1 > 330 and x2 > 330
    return
  end
  if y1 < -270 and y2 < -270
    return
  end
  if y1 > 270 and y2 > 270
    return
  end
  if abs(x1) > 1500 or abs(x2) > 1500 or abs(y1) > 1500 or abs(y2) > 1500
    clipln(x1, y1, x2, y2)
    return
  end
  goto(x1, y1)
  pendown()
  goto(x2, y2)
  penup()
end

# Liang-Barsky clip to a 3000 x 3000 box, for very long lines when zoomed in
def clipln(x1, y1, x2, y2)
  lt0 = 0
  lt1 = 1
  ldx = x2 - x1
  ldy = y2 - y1
  lok = 1
  clipe(0 - ldx, x1 + 1500)
  clipe(ldx, 1500 - x1)
  clipe(0 - ldy, y1 + 1500)
  clipe(ldy, 1500 - y1)
  if lok == 1 and lt0 <= lt1
    goto(x1 + lt0 * ldx, y1 + lt0 * ldy)
    pendown()
    goto(x1 + lt1 * ldx, y1 + lt1 * ldy)
    penup()
  end
end

def clipe(p, q)
  if p == 0
    if q < 0
      lok = 0
    end
  else
    lr = q / p
    if p < 0
      if lr > lt1
        lok = 0
      elif lr > lt0
        lt0 = lr
      end
    else
      if lr < lt0
        lok = 0
      elif lr < lt1
        lt1 = lr
      end
    end
  end
end

def psize(s)
  if s < 1
    pensize(1)
  else
    pensize(s)
  end
end

# filled rectangle with slightly rounded corners
def rect(x1, y1, x2, y2, col)
  pencolor(col)
  pensize(10)
  uyy = y1 + 5
  until uyy >= y2 - 5
    ln(x1 + 5, uyy, x2 - 5, uyy)
    uyy += 8
  end
  ln(x1 + 5, y2 - 5, x2 - 5, y2 - 5)
end

def tx(s, x, y)
  drawtext(s, x, y)
  lm = 0
end

def tstyle(size, al, val)
  tsize(size)
  talign(al, val)
end

def tcol(hue, bright, trans)
  tcolor(hue, bright)
  ttrans(trans)
end

# ------------------------------------------------------------------ rendering

def render()
  erase()
  lm = 0
  drawgrid()
  dk = 1
  repeat count(in_src)
    if in_comp[dk] > 0 and in_src[dk] > 1
      drawwire(dk)
    end
    dk += 1
  end
  if drag == 3
    drawpreview()
  end
  qk = 1
  repeat ncomp
    if c_type[qk] > 0
      drawcomp(qk)
    end
    qk += 1
  end
  if hovpin > 0 and (zone == 5 or drag == 3)
    if hovpk == 1
      qx = (out_x[hovpin] - camx) * zoom
      qy = (out_y[hovpin] - camy) * zoom
    else
      qx = (in_x[hovpin] - camx) * zoom
      qy = (in_y[hovpin] - camy) * zoom
    end
    pencolor(0x60ffffff)
    pensize(14)
    ln(qx, qy, qx, qy)
    pencolor(0xffffff)
    pensize(5)
    ln(qx, qy, qx, qy)
  end
  if zoom > 0.45
    qk = 1
    repeat ncomp
      if c_type[qk] > 0
        drawctext(qk)
      end
      qk += 1
    end
  end
  drawui()
end

var qk

def drawgrid()
  gs = 20
  while gs * zoom < 14
    gs = gs * 2
  end
  pensize(1)
  gx = floor((camx - 240 / zoom) / gs) * gs
  until (gx - camx) * zoom > 240
    if gx % (gs * 5) == 0
      pencolor(C_GRID2)
    else
      pencolor(C_GRID)
    end
    gsx = (gx - camx) * zoom
    ln(gsx, -180, gsx, 180)
    gx += gs
  end
  gx = floor((camy - 180 / zoom) / gs) * gs
  until (gx - camy) * zoom > 180
    if gx % (gs * 5) == 0
      pencolor(C_GRID2)
    else
      pencolor(C_GRID)
    end
    gsx = (gx - camy) * zoom
    ln(-240, gsx, 240, gsx)
    gx += gs
  end
end

def drawwire(k)
  route(k)
  wv = outv[in_src[k]]
  if wv == 1
    pencolor(C_GLOW)
    psize(7 * zoom)
    wirepath()
    if k == hovw or k == dw and drag == 5
      pencolor(C_WHOV)
    else
      pencolor(C_HIGH)
    end
  else
    if k == hovw or k == dw and drag == 5
      pencolor(C_LOWHOV)
    else
      pencolor(C_LOW)
    end
  end
  psize(2.5 * zoom)
  wirepath()
end

def wirepath()
  gk = 1
  repeat count(rpx) - 1
    ln((rpx[gk] - camx) * zoom, (rpy[gk] - camy) * zoom, (rpx[gk + 1] - camx) * zoom, (rpy[gk + 1] - camy) * zoom)
    gk += 1
  end
end

def drawpreview()
  if wkind == 1
    qx = (out_x[wfrom] - camx) * zoom
    qy = (out_y[wfrom] - camy) * zoom
  else
    qx = (in_x[wfrom] - camx) * zoom
    qy = (in_y[wfrom] - camy) * zoom
  end
  if hovpin > 0
    if hovpk == 1
      ux = (out_x[hovpin] - camx) * zoom
      uy = (out_y[hovpin] - camy) * zoom
    else
      ux = (in_x[hovpin] - camx) * zoom
      uy = (in_y[hovpin] - camy) * zoom
    end
    pencolor(C_WHOV)
  else
    ux = mx
    uy = my
    pencolor(0xaab8c6)
  end
  psize(2 * zoom)
  ln(qx, qy, ux, uy)
end

def drawcomp(c)
  ct = c_type[c]
  qx = (c_x[c] - camx) * zoom
  qy = (c_y[c] - camy) * zoom
  qm = (tp_hw[ct] + 14) * zoom
  if qx + qm < -240 or qx - qm > 240
    return
  end
  qm = (tp_hh[ct] + 14) * zoom
  if qy + qm < -180 or qy - qm > 180
    return
  end
  if ct == T_LABEL
    if c == hovc or c == dc and drag == 2
      pencolor(C_EDGE)
      psize(2 * zoom)
      ln(qx - c_w[c] * zoom, qy - c_param[c] * 0.6 * zoom, qx + c_w[c] * zoom, qy - c_param[c] * 0.6 * zoom)
    end
    return
  end
  if ct == T_HEX
    tn = outv[in_src[c_in0[c]]] + 2 * outv[in_src[c_in0[c] + 1]] + 4 * outv[in_src[c_in0[c] + 2]] + 8 * outv[in_src[c_in0[c] + 3]]
    segs = segtab[tn + 1]
  elif ct == T_SEG7
    segs = ""
    tj = 0
    repeat 7
      segs = join(segs, outv[in_src[c_in0[c] + tj]])
      tj += 1
    end
  end
  drawops(ct, c, qx, qy, zoom)
  if ct == T_TABLE
    # highlight the row that matches the current inputs
    ta = outv[in_src[c_in0[c]]]
    if in_src[c_in0[c] + 1] > 1
      tn = 2 * ta + outv[in_src[c_in0[c] + 1]]
    else
      tn = ta
    end
    pencolor(C_ROW)
    psize(10 * zoom)
    ln(qx - 20 * zoom, qy + (9 - 11 * tn) * zoom, qx + 34 * zoom, qy + (9 - 11 * tn) * zoom)
  end
end

## Each part type has a list of drawing ops (made by build.py):
##   kind 1 = line (a,b)-(c,d) with pen size e
##   kind 2 = colour class a (b = pin/segment index, c/d = colours)
def drawops(t, c, ox, oy, s)
  dvis = 1
  dk = tp_op0[t]
  repeat tp_opn[t]
    if op_k[dk] == 1
      if dvis == 1
        psize(op_e[dk] * s)
        ln(ox + op_a[dk] * s, oy + op_b[dk] * s, ox + op_c[dk] * s, oy + op_d[dk] * s)
      end
    else
      setcls(dk, c)
    end
    dk += 1
  end
end

def setcls(k, c)
  cc = op_a[k]
  dvis = 1
  if cc < 3
    if c == hovc and c > 0 or c == dc and drag == 2
      pencolor(op_d[k])
    else
      pencolor(op_c[k])
    end
  elif cc == 3 or cc == 4 or cc == 13
    cv = 0
    if c > 0
      if cc == 4
        cv = outv[c_out0[c] + op_b[k]]
      else
        cv = outv[in_src[c_in0[c] + op_b[k]]]
      end
    end
    if cv == 1
      pencolor(op_c[k])
    elif cc == 13
      dvis = 0
    else
      pencolor(op_d[k])
    end
  elif cc < 8
    if c > 0
      cv = c_state[c]
    else
      cv = 1
    end
    if cc == 5
      if cv == 1
        pencolor(op_c[k])
      else
        dvis = 0
      end
    elif cc == 6
      if cv == 0
        pencolor(op_c[k])
      else
        dvis = 0
      end
    else
      if cv == 1
        pencolor(op_c[k])
      else
        pencolor(op_d[k])
      end
    end
  elif cc < 10
    if c > 0
      cv = outv[in_src[c_in0[c]]]
      lp = c_param[c]
    else
      cv = 1
      lp = 1
    end
    if cc == 8
      if cv == 1
        pencolor(led_on[lp])
      else
        pencolor(led_off[lp])
      end
    else
      if cv == 1
        pencolor(led_glow[lp])
      else
        dvis = 0
      end
    end
  elif cc < 12
    if letter(op_b[k] + 1, segs) == 1
      pencolor(op_c[k])
    elif cc == 11
      dvis = 0
    else
      pencolor(op_d[k])
    end
  else
    pencolor(op_c[k])
  end
end

def drawctext(c)
  ct = c_type[c]
  qx = (c_x[c] - camx) * zoom
  qy = (c_y[c] - camy) * zoom
  if ct == T_LABEL
    qm = (c_w[c] + 10) * zoom
  else
    qm = (tp_hw[ct] + 60) * zoom
  end
  if qx + qm < -240 or qx - qm > 240
    return
  end
  qm = (tp_hh[ct] + 30) * zoom
  if qy + qm < -180 or qy - qm > 180
    return
  end
  if ct == T_LABEL
    tstyle(c_param[c] * zoom, "center", "middle")
    tcol(0, 100, 12)
    tx(c_label[c], qx, qy)
    return
  end
  if tp_txn[ct] > 0 and zoom > 0.5
    tcol(0, 100, 40)
    ck = tp_tx0[ct]
    repeat tp_txn[ct]
      if tx_al[ck] == 0
        tstyle(tx_sz[ck] * zoom, "left", "middle")
      elif tx_al[ck] == 1
        tstyle(tx_sz[ck] * zoom, "center", "middle")
      else
        tstyle(tx_sz[ck] * zoom, "right", "middle")
      end
      tx(tx_s[ck], qx + tx_x[ck] * zoom, qy + tx_y[ck] * zoom)
      ck += 1
    end
  end
  if ct == T_TABLE
    drawtable(c)
  elif ct == T_NUM
    tn = 0
    tj = 0
    cw = 1
    repeat 8
      tn += cw * outv[in_src[c_in0[c] + tj]]
      cw = cw * 2
      tj += 1
    end
    tstyle(22 * zoom, "center", "middle")
    tcol(37, 30, 0)
    tx(tn, qx + 8 * zoom, qy - 5 * zoom)
  elif ct == T_CLOCK
    tstyle(8 * zoom, "center", "top")
    tcol(0, 100, 45)
    tx(join("T=", c_param[c] * 2), qx, qy - 17 * zoom)
  end
  if c_label[c] != ""
    tcol(0, 100, 8)
    if tp_lpos[ct] == 1
      tstyle(11 * zoom, "right", "middle")
      tx(c_label[c], qx - (tp_hw[ct] + 5) * zoom, qy)
    elif tp_lpos[ct] == 2
      tstyle(11 * zoom, "left", "middle")
      tx(c_label[c], qx + (tp_hw[ct] + 5) * zoom, qy)
    else
      tstyle(11 * zoom, "center", "bottom")
      tx(c_label[c], qx, qy + (tp_hh[ct] + 4) * zoom)
    end
  end
end

def drawtable(c)
  ttxt = c_state[c]
  tstyle(8 * zoom, "center", "middle")
  tcol(0, 100, 40)
  if in_src[c_in0[c] + 1] > 1
    tx("A", qx - 12 * zoom, qy + 21 * zoom)
    tx("B", qx + 2 * zoom, qy + 21 * zoom)
    tx("Y", qx + 24 * zoom, qy + 21 * zoom)
    tcol(0, 100, 10)
    cw = 0
    repeat 4
      tx(floor(cw / 2), qx - 12 * zoom, qy + (9 - 11 * cw) * zoom)
      tx(cw % 2, qx + 2 * zoom, qy + (9 - 11 * cw) * zoom)
      tx(letter(cw + 1, ttxt), qx + 24 * zoom, qy + (9 - 11 * cw) * zoom)
      cw += 1
    end
  else
    tx("A", qx - 6 * zoom, qy + 21 * zoom)
    tx("Y", qx + 24 * zoom, qy + 21 * zoom)
    tcol(0, 100, 10)
    tx("0", qx - 6 * zoom, qy + 9 * zoom)
    tx(letter(1, ttxt), qx + 24 * zoom, qy + 9 * zoom)
    tx("1", qx - 6 * zoom, qy - 2 * zoom)
    tx(letter(3, ttxt), qx + 24 * zoom, qy - 2 * zoom)
  end
end

# ------------------------------------------------------------------ user interface

def drawui()
  # palette
  pencolor(C_PANEL)
  pensize(56)
  ln(-212, 200, -212, -200)
  pencolor(C_EDGE)
  pensize(1)
  ln(-184, 152, -184, -180)
  ui = 1
  repeat NT
    ux = -226 + 28 * ((ui - 1) % 2)
    uy = 140 - 26 * floor((ui - 1) / 2)
    if ui == hovp
      pencolor(C_BTNH)
      pensize(24)
      ln(ux - 1, uy, ux + 1, uy)
    end
    segs = "1111111"
    if ui != T_LABEL
      drawops(ui, 0, ux - tp_icx[ui] * tp_ics[ui], uy - tp_icy[ui] * tp_ics[ui], tp_ics[ui])
    end
    ui += 1
  end
  # toolbar + status bar backgrounds
  pencolor(C_PANEL)
  pensize(28)
  ln(-260, 167, 260, 167)
  pensize(15)
  ln(-184, -174, 260, -174)
  pencolor(C_EDGE)
  pensize(1)
  ln(-240, 152, 240, 152)
  ln(-184, -166, 240, -166)
  # buttons
  ub = 1
  repeat count(btn_x1)
    if btn_bg[ub] == 1
      if ub == hovb
        pencolor(C_BTNH)
      elif ub == 1 and running == 1
        pencolor(0x1f4a33)
      else
        pencolor(C_BTN)
      end
      uh = btn_y2[ub] - btn_y1[ub]
      pensize(uh)
      ln(btn_x1[ub] + uh / 2, (btn_y1[ub] + btn_y2[ub]) / 2, btn_x2[ub] - uh / 2, (btn_y1[ub] + btn_y2[ub]) / 2)
    elif ub == hovb
      pencolor(C_PANEL2)
      uh = btn_y2[ub] - btn_y1[ub]
      pensize(uh)
      ln(btn_x1[ub] + uh / 2, (btn_y1[ub] + btn_y2[ub]) / 2, btn_x2[ub] - uh / 2, (btn_y1[ub] + btn_y2[ub]) / 2)
    end
    ub += 1
  end
  # ---- texts
  tstyle(10, "center", "middle")
  tcol(0, 100, 0)
  ub = 1
  repeat count(btn_x1)
    ulab = btn_label[ub]
    if ub == 1
      if running == 1
        ulab = "Pause"
      else
        ulab = "Run"
      end
    elif ub == 14
      if demo > 0
        ulab = join(demo, join(". ", demo_name[demo]))
      else
        ulab = "Sandbox"
      end
    end
    tx(ulab, (btn_x1[ub] + btn_x2[ub]) / 2, (btn_y1[ub] + btn_y2[ub]) / 2)
    ub += 1
  end
  tcol(0, 100, 30)
  tx(speedname[speed], -108, 166)
  tstyle(14, "center", "middle")
  tcol(0, 100, 30)
  tx("T", -198, 140 - 26 * 8)
  # status bar
  tstyle(9, "left", "middle")
  tcol(0, 100, 35)
  if msgt > 0
    tcol(37, 30, 0)
    tx(msg, -178, -173)
    msgt -= 1
  else
    tx(hint, -178, -173)
  end
  tstyle(9, "right", "middle")
  tcol(0, 100, 50)
  tx(join("tick ", join(ticks, join("   ", join(round(zoom * 100), "%")))), 236, -173)
  # info panel
  if showinfo == 1 and demo > 0
    rect(-180, -164, 236, infotop, C_PANEL2)
    pencolor(C_ACCENT)
    pensize(2)
    ln(-176, infotop - 2, -176, -162)
    tstyle(12, "left", "top")
    tcol(37, 30, 0)
    tx(demo_name[demo], -168, infotop - 7)
    tstyle(10, "left", "top")
    tcol(0, 100, 12)
    drawtextw(demo_desc[demo], -168, infotop - 25, 396)
    lm = 0
  end
  if hovp > 0
    drawtooltip()
  end
  if help == 1
    drawhelp()
  end
  if exporting == 1
    rect(-200, 92, 200, 148, C_PANEL2)
    tstyle(10, "center", "top")
    tcol(37, 30, 0)
    tx("Circuit saved as a code (list monitor below)", 0, 140)
    tcol(0, 100, 15)
    drawtextw("Click the code in the list, press Ctrl+A then Ctrl+C to copy it. Use Load to paste it back later. Click the stage to close.", 0, 122, 380)
    lm = 0
  end
end

def drawtooltip()
  tstyle(10, "left", "top")
  measuretext(tp_desc[hovp], 200)
  uh = `TE height` + 30
  uy = 140 - 26 * floor((hovp - 1) / 2) + 12
  if uy - uh < -160
    uy = -160 + uh
  end
  rect(-180, uy - uh, 40, uy, C_PANEL2)
  pencolor(C_ACCENT)
  pensize(2)
  ln(-176, uy - 4, -176, uy - uh + 4)
  tstyle(11, "left", "top")
  tcol(37, 30, 0)
  tx(tp_name[hovp], -170, uy - 6)
  tstyle(10, "left", "top")
  tcol(0, 100, 12)
  drawtextw(tp_desc[hovp], -170, uy - 23, 200)
  lm = 0
end

def drawhelp()
  pencolor(0x99000000)
  pensize(600)
  ln(0, 0, 0, 0)
  rect(-222, -112, 222, 148, C_PANEL2)
  pencolor(C_ACCENT)
  pensize(2)
  ln(-212, 121, 212, 121)
  tstyle(14, "left", "top")
  tcol(37, 30, 0)
  tx("Logic Sim - how to use it", -210, 142)
  tstyle(9.5, "left", "top")
  tcol(0, 100, 10)
  ut = 1
  uy = 114
  repeat count(help_lines)
    drawtextw(help_lines[ut], -210, uy, 420)
    uy -= `TE height` + 3
    ut += 1
  end
  lm = 0
end
