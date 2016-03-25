from labrad import types as T

HEADER_TYPE = T.parseTypeTag('(ww)iww')
PACKET_TYPE = T.parseTypeTag('(ww)iws')
RECORD_TYPE = T.parseTypeTag('wss')

def packetStream(packetHandler, endianness='>'):
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
        context, request, source, length = T.unflatten(hdr, HEADER_TYPE, endianness=endianness)

        # get packet data
        while len(buf) < length:
            buf += yield 0
        s, buf = buf[:length], buf[length:]

        # unflatten the data
        records = unflattenRecords(s, endianness=endianness)

        packetHandler(source, context, request, records)

def unflattenPacket(data, endianness='>'):
    """Unflatten a single labrad packet"""
    hdr, rest = data[:20], data[20:]
    context, request, source, length = T.unflatten(hdr, HEADER_TYPE, endianness)
    assert len(rest) == length
    records = unflattenRecords(rest, endianness)
    return context, request, source, records

def unflattenRecords(data, endianness='>'):
    """Unflatten a list of records from the data segment of a packet"""
    records = []
    s = T.Buffer(data)
    while len(s):
        ID, tag, data = T.unflatten(s, RECORD_TYPE, endianness)
        rec = ID, T.FlatData(data, T.parseTypeTag(tag), endianness)
        records.append(rec)
    return records

def flattenPacket(target, context, request, records, endianness='>'):
    """Flatten a packet to the specified target."""
    if isinstance(records, str):
        data = records
    else:
        kw = {'endianness': endianness}
        data = ''.join(flattenRecord(*rec, **kw) for rec in records)
    flat = PACKET_TYPE.flatten((context, request, target, data), endianness)
    return flat.bytes

def flattenRecords(records, endianness='>'):
    kw = {'endianness': endianness}
    return ''.join(flattenRecord(*rec, **kw) for rec in records)

def flattenRecord(ID, data, types=[], endianness='>'):
    """Flatten a piece of data into a record with datatype and property."""
    try:
        flat = T.flatten(data, types, endianness)
    except T.FlatteningError as e:
        e.msg = e.msg + "\nSetting ID %s." % (ID,)
        raise
    flat_record = RECORD_TYPE.flatten((ID, str(flat.tag), str(flat.bytes)),
                                      endianness)
    return flat_record.bytes

