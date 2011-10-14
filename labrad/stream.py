from labrad import types as T

HEADER_TYPE = T.parseTypeTag('(ww)iww')
PACKET_TYPE = T.parseTypeTag('(ww)iws')
RECORD_TYPE = T.parseTypeTag('wss')

def packetStream(packetHandler):
    """A generator that assembles packets.

    Accepts a function packetHandler that will be called with four arguments
    whenever a packet is completed: source, context, request, records.
    """
    buf = ''
    while True:
        # get packet header (20 bytes)
        while len(buf) < 20:
            buf += yield 0
        hdr, buf = buf[:20], buf[20:]
        context, request, source, length = T.unflatten(hdr, HEADER_TYPE)

        # get packet data
        while len(buf) < length:
            buf += yield 0
        s, buf = buf[:length], buf[length:]

        # unflatten the data
        records = []
        s = T.Buffer(s)
        while len(s):
            ID, tag, data = T.unflatten(s, RECORD_TYPE)
            rec = ID, T.unflatten(data, tag)
            records.append(rec)
        packetHandler(source, context, request, records)

def flattenPacket(target, context, request, records):
    """Flatten a packet to the specified target."""
    if isinstance(records, str):
        data = records
    else:
        data = ''.join(flattenRecord(*rec) for rec in records)
    return PACKET_TYPE.__flatten__((context, request, target, data))

def flattenRecords(records):
    return ''.join(flattenRecord(*rec) for rec in records)

def flattenRecord(ID, data, types=[]):
    """Flatten a piece of data into a record with datatype and property."""
    s, t = T.flatten(data, types)
    return RECORD_TYPE.__flatten__((ID, str(t), str(s)))

