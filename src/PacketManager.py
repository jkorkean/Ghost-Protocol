'''
To do:
* Add variables for dynamic field size -> Not really possible anymore with TLV field
* Build a dictionary with TLVtypes for verification
*** Read TLV from rawdata: DONE ***
'''

import logging, struct

MAXPKTSIZE = 1400
TLVTYPESIZE = 1
TLVLENSIZE = 4
NULLTLV = 0xFF
TLVTYPE = {'TXCONTROL':1, 'DATACONTROL':2, 'DATA':3, 'SECURITY':4}
RAWTLVTYPE = {1:'TXCONTROL', 2:'DATACONTROL', 3:'DATA', 4:'SECURITY'}
OPERATION = {'HELLO':1, 'UPDATE':2, 'LIST':3, 'PULL':4, 'DATA':5, 'BYE':6}
CODE = {'REQUEST':1, 'RESPONSE':2}
REV_OPERATION = {1:'HELLO', 2:'UPDATE', 3:'LIST', 4:'PULL', 5:'DATA', 6:'BYE'}
REV_CODE = {1:'REQUEST', 2:'RESPONSE'}
#FLAG = {'ACK':1, 'URG':2, 'ECN':4, 'SEC':8}     #Not YET in use
#FLAG_REV = {1:'ACK', 2:'URG', 4:'ECN', 8:'SEC'} #Not YET in use

class PacketManager():
    def __init__(self):
        self.bytearrayTLV = ' '             #variable
        self.TLVs = []                      #variable
        self.logger = logging.getLogger("PacketManager")
        self.logger.debug("PacketManager created")

        self.version=1
        self.flags=0
        self.senderID=0
        self.txlocalID=0
        self.txremoteID=0
        self.sequence=0
        self.ack=0
        self.checksum = 0
        self.otype=0
        self.ocode=0
        self.TLVlist=[]
        self.rawdata=''


    def create_packet(self, version=1, flags=0, senderID=0, txlocalID=0, txremoteID=0,
                      sequence=0, ack=0, otype=0, ocode=0, TLVlist=None, rawdata=None):

        del self.TLVs[:]
        self.bytearrayTLV = ' '
        self.flag_list = flags

        if rawdata:
            self.packetize_raw(rawdata)
        else:
            self.version = version              #4 bit
            self.flags = 0                      #4 bit
            self.nextTLV = NULLTLV              #8 bit
            self.senderID = senderID            #16bit
            self.txlocalID = txlocalID          #16bit
            self.txremoteID = txremoteID        #16bit
            self.sequence = sequence            #32bit
            self.ack = ack                      #32bit
            if OPERATION.has_key(otype):
                self.otype = OPERATION[otype]   #8 bit
            else:
                self.ocode = 0
            if CODE.has_key(ocode):
                self.ocode = CODE[ocode]        #8 bit
            else:
                self.otype = 0

            self.checksum = 0                   #16bit

            if TLVlist is not None:
                self.append_list_to_TLVlist(TLVlist)

    def packetize_header(self, rawdata):
        del self.TLVs[:]
        self.bytearrayTLV = ' '

        unpacked_header = struct.unpack("!BBHHH", rawdata[0:8])
        (tmpbyte,self.nextTLV,self.senderID,self.txlocalID,self.txremoteID) = unpacked_header
        self.version = tmpbyte >> 4
        self.flags = tmpbyte & 0x0F
        return True

    def packetize_raw(self, rawdata):
        del self.TLVs[:]
        self.bytearrayTLV = ' '

        unpacked_header = struct.unpack("!BBHHHLLBBH", rawdata[0:20])
        (tmpbyte,self.nextTLV,self.senderID,self.txlocalID,self.txremoteID,self.sequence,self.ack,tmptype,tmpcode,self.checksum) = unpacked_header
        self.version = tmpbyte >> 4
        self.flags = tmpbyte & 0x0F

        if REV_OPERATION.has_key(tmptype):  self.otype = tmptype
        else:
            self.logger.error("[packetize_raw] Process failed!! Failed to recover proper TYPE! %d" % (tmptype))
            return False
        if REV_CODE.has_key(tmpcode):  self.ocode = tmpcode
        else:
            self.logger.error("[packetize_raw] Process failed!! Failed to recover proper CODE! %d" % (tmpcode))
            return False

        if not self.verify_checksum():
            self.logger.debug("[packetize_raw] Checksum failed!! Failed to recover packet header!")
            return False
        if self.nextTLV == NULLTLV:
            self.logger.debug("[packetize_raw] No TLVs in this packet!")
            return True

        i = 20
        ntype = 0
        while ntype != NULLTLV:
            clen = 0
            #For the first TLV the type is in the header
            if i == 20:
                ctype = self.nextTLV
            else:
                ctype = ntype

            ntype = ord(rawdata[i:i+TLVTYPESIZE])
            i+=TLVTYPESIZE
            for j in range(0,TLVLENSIZE):
                temp = rawdata[i]
                if ord(temp) == 0:
                    temp = '0'
                clen += 10**(TLVLENSIZE-j-1) * int(temp)
                i+=1
            cvalue = rawdata[i:i+clen]
            i+=clen
            self.append_entry_to_TLVlist(RAWTLVTYPE[ctype],cvalue)

        return True

    def create_TLV_entry(self, ttype, value):
        if len(value)>=10**TLVLENSIZE:
            self.logger.error("Error adding TLV %s:%s:%s" % (ttype, str(len(value)), value))
            return

        etype = TLVTYPE[ttype]
        elen = (TLVLENSIZE - len(str(len(value)))) * '0' + str(len(value))
        evalue = value
        return (etype,elen,evalue)

    def append_entry_to_TLVlist(self, ttype, value): #entry coded as (type,value)
        tlventry = self.create_TLV_entry(ttype, value)
        if tlventry != None and self.get_packet_length() < MAXPKTSIZE:
            self.TLVs.append(tlventry)
            return True

        if tlventry == None:
            print '1'
        if self.get_packet_length() >= MAXPKTSIZE:
            print '2'
        print "Failed to add TVL: %s, %s" % (ttype, value)
        exit(0)
        return False

    def append_list_to_TLVlist(self, ttype, infolist): #infolist coded as [value,value...]
        remaining_items = []
        for item in infolist:
            if self.get_packet_length() < MAXPKTSIZE:
                tlventry = self.create_TLV_entry(ttype, item)
                self.TLVs.append(tlventry)
            else:
                remaining_items.append(item)

        if len(remaining_items) != 0:
            print "The following TLV(s) could not be added:", remaining_items
        return remaining_items

    def purge_tlvs(self, ttype = ""):
        self.TLVs[:] = [tlv for tlv in self.TLVs if not (ttype == "" or TLVTYPE[ttype] == tlv[0])]

    def get_version(self):
        return self.version

    def get_flags(self):
        flaglist = []
        if self.flags & 8 == 8:
            flaglist.append('SEC')
        if self.flags & 4 == 4:
            flaglist.append('ECN')
        if self.flags & 2 == 2:
            flaglist.append('CRY')
        if self.flags & 1 == 1:
            flaglist.append('ACK')
        return flaglist

    def get_senderID(self):
        return self.senderID

    def get_txlocalID(self):
        return self.txlocalID

    def get_txremoteID(self):
        return self.txremoteID

    def get_sequence(self):
        return self.sequence

    def get_ack(self):
        return self.ack

    def get_otype(self):
        return REV_OPERATION[self.otype]

    def get_ocode(self):
        return REV_CODE[self.ocode]

    def get_TLVlist(self, tlvtype=""):
        tmplist = []
        for item in self.TLVs:
            #tmplist.append((RAWTLVTYPE[item[0]],item[2]))
            if tlvtype == "" or TLVTYPE[tlvtype] == item[0]:
                tmplist.append(item[2])
        return tmplist

    def get_TLVlist_typevalue(self):
        tmplist = []
        for item in self.TLVs:
            tmplist.append((RAWTLVTYPE[item[0]],item[2]))
        return tmplist


    def calculate_checksum(self):
        #tempsum = 0L

        subchunk1 = (self.version << 4 | self.flags) << 8 | self.nextTLV
        subchunk2 = int(self.sequence >> 8)
        subchunk3 = int(self.sequence & 0xFF)
        subchunk4 = int(self.ack >> 8)
        subchunk5 = int(self.ack & 0xFF)
        subchunk6 = self.otype << 8 | self.ocode

        tempsum = subchunk1 + self.senderID + self.txlocalID + self.txremoteID + subchunk2 +\
        subchunk3 + subchunk4 + subchunk5 + subchunk6

        tempcarry = tempsum >> 16
        tempsum = tempcarry + (tempsum & 0xFFFF)
        tempsum = ~tempsum & 0xFFFF
        return tempsum


    def verify_checksum(self):
        calculated_checksum = self.calculate_checksum()

        if calculated_checksum == self.checksum:
            self.logger.debug("Checksum verification successful!!")
            return True
        else:
            self.logger.error("Checksum verification failed!!")
            return False

    def build_TLVs(self):
        tempstring = ''
        i=0

        if len(self.TLVs) == 0:
            self.logger.debug("There are no TLVs to build")
            return

        while i < len(self.TLVs):
            item = self.TLVs[i]
            if i==0:
                self.nextTLV = item[0] #NextTLV field is type of the first TLV
            #Check whether are not at the last element
            if i+1 == len(self.TLVs):
                #Setting value for NULL next TLV
                tempstring += struct.pack("!B", NULLTLV)
            else:
                #Append type of the next element
                tempstring += struct.pack("!B", self.TLVs[i+1][0])
            #for j in item[1]:
            #    tempstring += struct.pack("!B", ord(j))
            #for j in item[2]:
            #    tempstring += struct.pack("!B", ord(j))
            tempstring += item[1]
            tempstring += item[2]
            i+=1

        self.bytearrayTLV = tempstring

    def build_FLAGs(self):
        flagvalue = 0

        if len(self.flag_list) == 0:
            self.logger.debug("There are no FLAGs to build")
            del self.flag_list[:]
            return
        #FLAG = {'ACK':1, 'URG':2, 'ECN':4, 'SEC':8}
        else:
            for item in self.flag_list:
                if item == 'ACK':
                    flagvalue += 1
                elif item == 'CRY':
                    flagvalue += 2
                elif item == 'ECN':
                    flagvalue += 4
                elif item == 'SEC':
                    flagvalue += 8

            self.flags = flagvalue

    def build_packet(self):
        #First build TLV so the field nextType is filled
        self.build_TLVs()
        #Then build the FLAGs
        self.build_FLAGs()

        #Then we can calculate the checksum for the protocol header
        self.checksum = self.calculate_checksum()
        byte1 = self.version << 4 | self.flags
        #Now we can proceed packing the whole structure for network transferring
        packet = struct.pack("!BBHHHLLBBH",byte1,self.nextTLV,self.senderID,self.txlocalID,self.txremoteID,self.sequence,self.ack,self.otype,self.ocode,self.checksum)+self.bytearrayTLV
        return packet

    def get_packet_length(self):
        packet_size = 20
        for item in self.TLVs:
            packet_size += (len(item[2])+5)
        return packet_size

    def __str__(self):
        ret = "version: '%s':'%x'\n" % (self.version,self.version)
        ret += "flags: '%s':'%x'\n" % (self.flags,self.flags)
        ret += "nextTLV: '%s':'%.2x'\n" % (self.nextTLV,self.nextTLV)
        ret += "senderID: '%s':'%.2x'\n" % (self.senderID,self.senderID)
        ret += "txlocalID: '%s':'%.2x'\n" % (self.txlocalID,self.txlocalID)
        ret += "txremoteID: '%s':'%.2x'\n" % (self.txremoteID,self.txremoteID)
        ret += "sequence: '%s':'%.2x'\n" % (self.sequence,self.sequence)
        ret += "ack: '%s':'%.2x'\n" % (self.ack,self.ack)
        ret += "otype: '%s':'%.2x'\n" % (REV_OPERATION[self.otype],self.otype)
        ret += "ocode: '%s':'%.2x'\n" % (REV_CODE[self.ocode],self.ocode)
        ret += "checksum: '%s':'%.2x'\n" % (self.checksum,self.checksum)
        if self.TLVs:
            ret += "tlvs:\n"
            ret += "\n".join(["%s:%s:%s" % (RAWTLVTYPE[tlv[0]], tlv[1], tlv[2]) for tlv in self.TLVs])
        else:
            ret += 'no tlvs'

        return ret

    def hex_packet(self):
        packet = self.build_packet()
        x=str(packet)
        l = len(x)
        i = 0
        while i < l:
            print "%04x  " % i,
            for j in range(16):
                if i+j < l:
                    print "%02X" % ord(x[i+j]),
                else:
                    print "  ",
                if j%16 == 7:
                    print "",
            print " ",

            ascii = x[i:i+16]
            r=""
            for i2 in ascii:
                j2 = ord(i2)
                if (j2 < 32) or (j2 >= 127):
                    r=r+"."
                else:
                    r=r+i2
            print r
            i += 16
        print ''

    @staticmethod
    def hex_data(packet):
        x=str(packet)
        l = len(x)
        i = 0
        while i < l:
            print "%04x  " % i,
            for j in range(16):
                if i+j < l:
                    print "%02X" % ord(x[i+j]),
                else:
                    print "  ",
                if j%16 == 7:
                    print "",
            print " ",

            ascii = x[i:i+16]
            r=""
            for i2 in ascii:
                j2 = ord(i2)
                if (j2 < 32) or (j2 >= 127):
                    r=r+"."
                else:
                    r=r+i2
            print r
            i += 16
        print ''


class OutPacket(PacketManager):
    send_time = 0.0
    resends = 0
    no_enc = False
    def __init__(self, no_enc = False):
        PacketManager.__init__(self)
        self.no_enc = no_enc

class InPacket(PacketManager):
    receive_time = 0.0
    def __init__(self):
        PacketManager.__init__(self)

