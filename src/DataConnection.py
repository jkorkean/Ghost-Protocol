import logging, socket, random, select, sys, time, os, hashlib, subprocess
from threading import Thread

from PacketManager import *
from Connection import *
from FileSystem import *

class DataServer(Thread):

    sock = None
    logger = None
    received_packet = None
    buffer_size = 2048
    session_list = []
    kill_flag = False

    def __init__(self, folder, ip = "", port = "", use_enc = False, p = 0.0, q = 0.0):
        Thread.__init__(self)
        self.ip=ip
        self.port=port
        self.folder = folder
        self.use_enc = use_enc

        if not ip: ip = '0.0.0.0'
        if not port: port = random.randint(4500, 4600)

        self.logger = logging.getLogger("Data server: ip %s, port %s" % (ip,port))

        try:
            self.sock = LossySocket(socket.AF_INET, socket.SOCK_DGRAM, p, q)
            self.sock.bind((ip, port))
            #self.sock.setblocking(0) # non-blocking
        except socket.error:
                print("Error with socket")

        self.received_packet = InPacket()

    def run(self):
        timeout = 1
        while not self.kill_flag:
            #input = select.select(self.read_list,[],[],timeout)
            buffer, addr = self.sock.recvfrom(2000)
            # Data handling or timeout

            #if input == ([], [], []):
            #if len(buffer) == 0:
                # print timeout
 
                # remove old sessions
            for session in self.session_list:

                if session.status==1 or session.status==2:
                    self.session_list.remove(session)
                    # check if we need to resend something
                else:
                       # session.check_timeout()
                   pass


            #for s in input:
            #for r in self.read_list:
            #if s == [r]:
            #try:
            #    buffer, addr = r.recvfrom(self.buffer_size)
            
            if self.use_enc:
                self.received_packet.packetize_header(buffer)
            else:
                self.received_packet.packetize_raw(buffer)

            for session in self.session_list:
                if self.received_packet.txremoteID == session.local_session_id and self.received_packet.txlocalID == session.remote_session_id:
                    if self.use_enc:
                        try:
                            buffer = session.connection.security.decrypt_AES_bin(session.connection.aes_key, buffer, 8)
                            if not self.received_packet.packetize_raw(buffer):
                                self.logger.warning('Invalid data in encrypted data packet!')
                                break
                        except:
                            self.logger.warning('Invalid data in encrypted data packet!')
                            break

                    session.connection.receive_packet_start(self.received_packet)
                    session.handle(self.received_packet)
                    session.connection.receive_packet_end(self.received_packet,session.sender_id)


    def kill_server(self):
        self.kill_flag=True

    def add_session(self, remote_ip, remote_port, local_session_id, remote_session_id, version, sender_id, file_path, md5sum, size, is_request, security = None, aes_key = None):
        if is_request:
            connection = Connection(self.sock, remote_ip, remote_port, local_session_id, remote_session_id,version, 0, 1, logger = self.logger, security = security, aes_key = aes_key, use_enc = self.use_enc)
        else:
            connection = Connection(self.sock, remote_ip, remote_port, local_session_id, remote_session_id,version, 1, 0, logger = self.logger, security = security, aes_key = aes_key, use_enc = self.use_enc)
        data_session = DataSession(remote_ip, remote_port, local_session_id, remote_session_id, version, sender_id, file_path, md5sum, size, self.folder, connection, 0, logger = self.logger)

        fail = False
        for session in self.session_list:
            
            if session.local_session_id==data_session.local_session_id and session.remote_session_id==data_session.remote_session_id:
                #print("ignore session, it's already there")
                fail=True
                pass

        if fail == False:
            self.session_list.append(data_session)
        if is_request == True:
            to_chunk = data_session.get_chunk_count()
            data_session.data_req(1,to_chunk) # ask for the whole file

    def add_port(self, new_port=""):
        self.new_port=new_port

        if not new_port:
            new_port = random.randint(4500, 4600)
        if len(self.port_list)==100:
            return

        run = True
        while (run):
            temp = False
            for x in self.port_list:
                if x[0] == new_port:
                    new_port = random.randint(4500, 4600)
                    #print("Port already in use")
                    temp = True

            if temp == True:
                run = True
            else:
                run = False # port was added successfully

        self.logger = logging.getLogger("Data session to: port %s" % (new_port))
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind((self.ip, new_port))
            #self.sock.setblocking(0) # non-blocking
            self.port_list.append([new_port,self.sock])
            self.read_list.append(self.sock)
        except socket.error:
                self.logger.alarm("Error with socket")

    def remove_port(self, old_port):
        self.old_port=old_port

        try:
            rm = [x[0] for x in self.port_list].index(old_port)
            temp_val=self.port_list.pop(rm)
            self.read_list.remove(temp_val[1])
        except:
            pass

    def get_port(self):
        return self.port
        #from random import choice
        #retval=choice(self.port_list)
        #return retval[0]


class DataSession():

    packet = None
    chunk_size = 1000.0
    temp_file_path = None
    allocated = False
    chunks_to_receive = []
    failed_chunks = {}
    timeout = 0
    #status: 0 = processing, 1 = ready, 2 = failed

    def __init__(self, remote_ip, remote_port, local_session_id, remote_session_id, version, sender_id, file_path, md5sum, size, folder, connection, status=0, logger = None):

        self.remote_ip = remote_ip
        self.remote_port = remote_port
        self.local_session_id = local_session_id
        self.remote_session_id = remote_session_id
        self.version = version
        self.sender_id = sender_id
        self.file_path = file_path
        self.md5sum = md5sum
        self.size = size # in bytes
        self.folder = folder
        self.status = status
        #a temp file location
        self.temp_file_path = self.folder+"/.private/file_"+str(self.local_session_id)+str(self.remote_session_id)+str(self.sender_id)+".temp"
        self.initialize_transfer()
        self.connection=connection
        self.logger = logger

    def initialize_transfer(self):
        max = self.get_chunk_count()
        for x in range(1, max+1):
            self.chunks_to_receive.append(x)

    def transfer_status(self):
        if len(self.chunks_to_receive)==0:
            return True
        else:
            return False

    def finish(self):
        if self.md5sum==self.get_md5sum_file(self.temp_file_path):
            print("file transferred successfully")
            self.ensure_folder_structure(self.file_path)
            os.rename(self.temp_file_path, self.folder+'/'+self.file_path)
            self.status=1 #ready
        else:
            os.remove(self.temp_file_path)
            self.status=2 #failed
        #bye
        self.bye_req()

    def check_timeout(self):
        # check if too much time is passed and remove session if necessary
        self.timeout=self.timeout+1        
       
        if self.timeout>1000:
            self.status=2
            self.bye_req()
            return
        elif len(self.failed_chunks)==0:
            return
        elif max(self.failed_chunks, key=self.failed_chunks.get)>5:
            self.status=2
            self.bye_req()
        else:
            packet_to_send = OutPacket()
            packet_to_send.create_packet(version=self.version, flags=[0],senderID=self.sender_id, txlocalID=self.local_session_id, txremoteID=self.remote_session_id, otype='DATA', ocode='REQUEST')
            packet_to_send.append_entry_to_TLVlist('DATA', self.file_path)

            for chunk in self.failed_chunks.itervalues():
                packet_to_send.append_entry_to_TLVlist('DATACONTROL', 'from?%d' %chunk +'?to?%d' %chunk)

            while True:
                status=self.connection.send_packet_reliable(packet_to_send)
                if status==True:
                    break

    def handle(self, packet):
        self.packet = packet
        from_chunk = None
        to_chunk = None
        from_ok = 0
        to_ok = 0
        self.timeout = 0

        if packet.otype == OPERATION['BYE'] and packet.ocode == CODE['REQUEST']:
            self.status=1
            self.bye_response()
        elif packet.otype == OPERATION['BYE'] and packet.ocode == CODE['RESPONSE']:
            pass
        elif self.status==1 or self.status==2:
            return
        elif packet.otype == OPERATION['DATA'] and packet.ocode == CODE['RESPONSE']:
            #print("response received")
            data = packet.get_TLVlist('DATA') # actual data
            #check md5sum
            control = packet.get_TLVlist('DATACONTROL')
            value = control[0].split('?')
            # value[0] ="id", value[1]= id, value[2]=md5sum
            if value[2]==self.get_md5sum(data[0]): #md5sum is ok
                #print("md5sum matched "+value[1])
                # Check if the chunk is already received and ignore it if necessary
                if int(value[1]) in self.chunks_to_receive:
                    self.chunks_to_receive.remove(int(value[1]))

                if self.failed_chunks.get(int(value[1]))==None:
                    pass
                else:
                    del self.failed_chunks[value[1]]
            else:
                print("md5sum mismatched")
                if self.failed_chunks.get(value[1])==None:
                    self.failed_chunks[value[1]] = 1
                else:
                    self.failed_chunks[value[1]] += 1

            if self.allocated == False:
                self.allocate_file(self.temp_file_path)
                self.allocated = True

            self.construct_file(self.temp_file_path,int(value[1]),data[0])

            if self.transfer_status()==True:
                #print("done")
                self.finish()

        elif packet.otype == OPERATION['DATA'] and packet.ocode == CODE['REQUEST']:
            #print("request received")
            data = packet.get_TLVlist('DATA')
            # verify that file path (data[0]) is valid
            if data[0]==self.file_path:
                pass
            else:
                return

            tlvlist = packet.get_TLVlist('DATACONTROL')
            for tlv in tlvlist:
                temp = tlv.split('?')
                if temp[0] == 'from':
                    from_chunk=temp[1]
                    print("from chunk")
                    print(from_chunk)
                    from_ok = 1
                if temp[2] == 'to':
                    to_chunk=temp[3]
                    print("to chunk")
                    print(to_chunk)
                    to_ok = 1
                if from_ok==1 and to_ok==1:
                    self.data_response(int(from_chunk),int(to_chunk))
                    from_ok = 0
                    to_ok = 0
        else:
            pass

    def bye_req(self):
        packet_to_send = OutPacket()
        packet_to_send.create_packet(version=self.version, flags=[0],senderID=self.sender_id, txlocalID=self.local_session_id, txremoteID=self.remote_session_id, otype='BYE', ocode='REQUEST')

        self.logger.info('BYE request, stopping')

        while True:
            status=self.connection.send_packet_reliable(packet_to_send)
            if status==True:
                break
            print '1'

    def bye_response(self):
        packet_to_send = OutPacket()
        packet_to_send.create_packet(version=self.version, flags=[0],senderID=self.sender_id, txlocalID=self.local_session_id, txremoteID=self.remote_session_id, otype='BYE', ocode='RESPONSE')

        self.logger.info('BYE response, stopping')

        while True:
            status=self.connection.send_packet_reliable(packet_to_send)
            if status==True:
                break
            print '2'

    def data_req(self,from_chunk,to_chunk):

        packet_to_send = OutPacket()
        packet_to_send.create_packet(version=self.version, flags=[0],senderID=self.sender_id, txlocalID=self.local_session_id, txremoteID=self.remote_session_id, otype='DATA', ocode='REQUEST')
        packet_to_send.append_entry_to_TLVlist('DATA', self.file_path)
        packet_to_send.append_entry_to_TLVlist('DATACONTROL', 'from?%d' % from_chunk +'?to?%d' %to_chunk)


        while True:
            status=self.connection.send_packet_reliable(packet_to_send)
            if status==True:
                break
            print '3'

    def data_response(self,from_chunk, to_chunk):

        for x in range(from_chunk, to_chunk+1):
            packet_to_send = OutPacket()
            packet_to_send.create_packet(version=self.version, flags=[0], senderID=self.sender_id, txlocalID=self.local_session_id, txremoteID=self.remote_session_id, otype='DATA', ocode='RESPONSE')

            chunk=self.get_chunk(x)
            packet_to_send.append_entry_to_TLVlist('DATA', chunk)
            packet_to_send.append_entry_to_TLVlist('DATACONTROL','id?%d?' %x + self.get_md5sum(chunk))

            received_packet = InPacket()

            while True:
                status=self.connection.send_packet_reliable(packet_to_send)
                self.connection.sock.setblocking(0)
                try:
                    while True:
                        buffer, addr = self.connection.sock.recvfrom(2048)
                        #print 'data received:'
                        #print PacketManager.hex_data(buffer)
                        
                        if self.connection.use_enc:
                            received_packet.packetize_header(buffer)
                        else:
                            received_packet.packetize_raw(buffer)
                        # check & confirm that session is valid
                        if received_packet.txremoteID == self.connection.local_session_id and received_packet.txlocalID == self.connection.remote_session_id:
                            if self.connection.use_enc:
                                try:
                                    buffer = self.connection.security.decrypt_AES_bin(self.connection.aes_key, buffer, 8)
                                    if not received_packet.packetize_raw(buffer):
                                        self.logger.warning('Invalid data in encrypted data packet!')
                                        break
                                except:
                                    self.logger.warning('Invalid data in encrypted data packet!')
                                    break
                            self.connection.receive_packet_start(received_packet)
                    print '4'
                except socket.error:
                    pass
                self.connection.sock.setblocking(1)
                if status==True:
                    break
                time.sleep(0.01)


            #self.socket.sendto(packet_to_send.build_packet(), (self.remote_ip,self.remote_port))
            #time.sleep(0.01)

    def ensure_folder_structure(self,file_path):
        d = os.path.dirname(self.folder+"/"+file_path)
        if not os.path.exists(d):
            os.makedirs(d)

    def get_md5sum(self, data):
        md5 = hashlib.md5()
        md5.update(data)
        return md5.hexdigest()

    def get_md5sum_file(self,filename, block_size=2**20):
        file = open(filename, 'r')
        md5 = hashlib.md5()
        while True:
            data = file.read(block_size)
            if not data:
                break
            md5.update(data)
        file.close()
        return md5.hexdigest()

    def get_chunk_count(self):
        chunks = self.size/self.chunk_size
        rounded = round(chunks)

        if chunks - rounded > 0:
            return int(rounded + 1)
        else:
            return int(rounded)

    def get_chunk(self,id):
        try:
            f = open(self.folder+"/"+self.file_path, "r")
            f.seek((id-1)*int(self.chunk_size))
            chunk = f.read(int(self.chunk_size))
            f.close()
            return chunk
        except:
            pass

    def get_size(self):
        return os.path.getsize(self.folder+"/"+self.file_path)

    def allocate_file(self,new_file):
        try:
            f = open(new_file, "wb")
            f.write("\0" * self.size)
            f.close()
        except:
            pass

    def construct_file(self,new_file,id,chunk):
        try:
            f = open(new_file, "r+")
            f.seek((id-1)*int(self.chunk_size))
            f.write(chunk)
            f.close()

        except:
            pass

def main():

    if len(sys.argv) == 6 and sys.argv[1] == "-c":
        print 'Starting client'
        client = True
        lport = 5000
        rport = 6000
        p = float(sys.argv[2])
        q = float(sys.argv[3])
        folder = sys.argv[4]
        sfolder = sys.argv[5]
        size = 5830917
        f = 'testi/test.txt'
        h = "d0cdb43bed5c4dcdaae6edc6e477a00a"
        #h = str(FileSystem.get_md5sum_hex(sfolder+f))
        lses = 111
        rses = 222
    elif len(sys.argv) == 5 and sys.argv[1] == "-s":
        print 'Starting server'
        client = False
        lport = 6000
        rport = 5000
        p = float(sys.argv[2])
        q = float(sys.argv[3])
        folder = 'folder2'
        #size = int(sys.argv[4])
        size = 5830917
        f = 'testi/test.txt'
        #subprocess.call(['dd', 'if=/dev/urandom', 'of=%s' % (folder+f), 'bs=%d' % size, 'count=1'])
        #h = str(FileSystem.get_md5sum_hex(folder+f))
        h = "d0cdb43bed5c4dcdaae6edc6e477a00a"
        lses = 222
        rses = 111
    else:
        sys.exit("Args: [server -s, or client -c] [p value] [q value] <folder for server> <filesize for client> <server's folder for client>")

    data_server = DataServer(folder,'0.0.0.0',lport)
    data_server.start()
    #data_server.add_port()
    #data_server.remove_port(4500)

    #port = data_server.get_port()

    data_server.add_session('0.0.0.0', rport,lses,rses,1,10,f,h,size,client)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print 'CTRL+C received, killing data server...'
        data_server.kill_server()
        #if client:
            #subprocess.call(['rm', '%s' % f])


if __name__ == '__main__':
    main()
