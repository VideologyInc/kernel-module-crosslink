#! /bin/bash
# hacky script which answers an upcall from the crosslink kernel module to chnage the resolution.
# this needs to be changed to either:
# 1: i2c-to-uart inside the crosslink to take care of visca.
# 2: a serdev v4l2 subdev driver which chains with the crosslink one.
# 3: at least a V4L2_EVENT_SOURCE_CHANGE event chnage listener in userspace to replace this script.

port="/dev/ttymxc3"

log=/dev/stdout
has_i2c_serial=""

function write_check() {
    echo "Writing $1"
    for _ in {0..20}; do
        if [[ -n "${has_i2c_serial}" ]]; then
            res=$(vdlg-lvds-visca -d /dev/links/crosslink_mipi_1 "$1")
        else
            res=$(serial-xfer 9600 "$port" "$1")
        fi
        echo $res >> $log
        sleep 0.1
        [[ "$res" == *"9041ff"* ]] && break
    done
}

    # Sony
function Sony() {
    if [ ! -z "$1" ]; then

         # 720P25 Sony FCB-EV9520L
        [ "$1" == "0x03" ] && write_check "81010424720101FF" && write_check "81010424740000FF" && write_check "8101041903FF" && echo "Sony 720P25"  >> $log
        # 720P30 Sony FCB-EV9520L
        [ "$1" == "0x02" ] && write_check "8101042472000FFF" && write_check "81010424740000FF" && write_check "8101041903FF" && echo "Sony 720P30"  >> $log
        # 720P50 Sony FCB-EV9520L
        [ "$1" == "0x01" ] && write_check "8101042472000CFF" && write_check "81010424740000FF" && write_check "8101041903FF" && echo "Sony 720P50"  >> $log
        # 720P60 Sony FCB-EV9520L
        [ "$1" == "0x00" ] && write_check "8101042472000AFF" && write_check "81010424740000FF" && write_check "8101041903FF" && echo "Sony 720P60"  >> $log
        # 1080P25 Sony FCB-EV9520L
        [ "$1" == "0x13" ] && write_check "81010424720008FF" && write_check "81010424740000FF" && write_check "8101041903FF" && echo "Sony 1080P25" >> $log
        # 1080P30 Sony FCB-EV9520L
        [ "$1" == "0x12" ] && write_check "81010424720007FF" && write_check "81010424740000FF" && write_check "8101041903FF" && echo "Sony 1080P30" >> $log
        # 1080p50 Sony FCB-EV9520L
        [ "$1" == "0x93" ] && write_check "81010424720104FF" && write_check "81010424740001FF" && write_check "8101041903FF" && echo "Sony 1080P50" >> $log
        # 1080p60 Sony FCB-EV9520L
        [ "$1" == "0x92" ] && write_check "81010424720105FF" && write_check "81010424740001FF" && write_check "8101041903FF" && echo "Sony 1080P60" >> $log
    fi

    for _ in {0..50}; do
        if [[ -n "${has_i2c_serial}" ]]; then
            res=$(vdlg-lvds-visca -d /dev/links/crosslink_mipi_1 "81090400FF")
        else
            res=$(serial-xfer 9600 "$port" "81090400FF")
        fi

        [[ "$res" == *"9050"* ]] && break
    done
}

function ZoomBlock_dual() {
    if [ ! -z "$1" ]; then
        # 720P25
        [ "$1" == "0x03" ] && write_check "81010424720101FF" && write_check "81010424740000FF"  && echo "ZoomBlock 720P25" >> $log
        # 720P30
        [ "$1" == "0x02" ] && write_check "8101042472000EFF" && write_check "81010424740000FF"  && echo "ZoomBlock 720P30" >> $log
        # 720P50
        [ "$1" == "0x01" ] && write_check "8101042472000CFF" && write_check "81010424740000FF"  && echo "ZoomBlock 720P50" >> $log
        # 720P60
        [ "$1" == "0x00" ] && write_check "81010424720009FF" && write_check "81010424740000FF"  && echo "ZoomBlock 720P60" >> $log
        # 1080P25
        [ "$1" == "0x13" ] && write_check "81010424720008FF" && write_check "81010424740000FF"  && echo "ZoomBlock 1080P25" >> $log
        # 1080P30
        [ "$1" == "0x12" ] && write_check "81010424720006FF" && write_check "81010424740000FF"  && echo "ZoomBlock 1080P30" >> $log
        # 1080p50
        [ "$1" == "0x93" ] && write_check "81010424720104FF" && write_check "81010424740001FF"  && echo "ZoomBlock 1080P50" >> $log
        # 1080p60
        [ "$1" == "0x92" ] && write_check "81010424720103FF" && write_check "81010424740001FF"  && echo "ZoomBlock 1080P60" >> $log
    fi
}

function ZoomBlock_single() {
    if [ ! -z "$1" ]; then
        # 720P25
        [ "$1" == "0x03" ] && write_check "81010424720101FF" && echo "ZoomBlock 720P25" >> $log
        # 720P30
        [ "$1" == "0x02" ] && write_check "8101042472000EFF" && echo "ZoomBlock 720P30" >> $log
        # 720P50
        [ "$1" == "0x01" ] && write_check "8101042472000CFF" && echo "ZoomBlock 720P50" >> $log
        # 720P60
        [ "$1" == "0x00" ] && write_check "81010424720009FF" && echo "ZoomBlock 720P60" >> $log
        # 1080P25
        [ "$1" == "0x13" ] && write_check "81010424720008FF" && echo "ZoomBlock 1080P25" >> $log
        # 1080P30
        [ "$1" == "0x12" ] && write_check "81010424720006FF" && echo "ZoomBlock 1080P30" >> $log
        # 1080p50
        [ "$1" == "0x93" ] && write_check "81010424720104FF" && echo "ZoomBlock 1080P50" >> $log
        # 1080p60
        [ "$1" == "0x92" ] && write_check "81010424720103FF" && echo "ZoomBlock 1080P60" >> $log
    fi
}

# check if this board has i2c-serial
crosslink_uart_status=$(i2cget -y -f 1 0x1c 0x9)
if (( $crosslink_uart_status >= 0x40 )); then
    has_i2c_serial="crosslink_has_Serial"
fi

# check if Sony or Not
if [[ -n "${has_i2c_serial}" ]]; then
    res=$(vdlg-lvds-visca -d /dev/links/crosslink_mipi_1 "81090002FF")
else
    res=$(serial-xfer 9600 "$port" "81090002FF")
fi

# clear log
echo $res > $log
if [[ "$res" == *"0711"* ]]; then
    Sony $1
elif [[ "$res" == *"0466"* ]]; then
    ZoomBlock_dual $1
    # ZoomBlock_single $1
else
    echo "Unknown camera" >> $log
fi
