import logging, getpass, os

class Configuration():
    param = 0
    default_port = 4321
    port = 0
    p_prob = 0.0
    q_prob = 0.0
    folder = ''
    peers = []

    def __init__(self, args):
        self.logger = logging.getLogger("Configuration")
        self.param = args
        self.passwd = ''

    def load_configuration(self):
        i=1
        temp_list=[]
        argv_len = len(self.param)
        while (i<argv_len):
            if str(self.param[i]) == '-t':
                self.port = int(str(self.param[i+1]))
            elif str(self.param[i]) == '-p':
                self.p_prob = float(str(self.param[i+1]))
            elif str(self.param[i]) == '-q':
                self.q_prob = float(str(self.param[i+1]))
            elif str(self.param[i]) == '-f':
                self.folder = str(self.param[i+1])
            elif str(self.param[i]) == '-pw':
                self.passwd = str(self.param[i+1])
            else:
                temp_list.append(str(self.param[i]))
                i-=1
            i+=2


        if not self.port:
            self.logger.warning("Local port not set, using default value")
            self.port=self.default_port
            print "Listening on default UDP port:", self.port

        if self.folder is not '':
            if self.folder.startswith('/'):
                self.folder = self.folder[1:]
            if self.folder.startswith('./'):
                self.folder = self.folder[2:]
            if self.folder.endswith('/'):
                self.folder = self.folder[:-1]
            self.folder = os.path.join(os.getcwd(),self.folder)
        else:
            self.folder = os.getcwd()

        for peer in temp_list:
            #Process peer list and extract IP:port per peer.
            if ':' in peer:
                ip = peer.split(':')[0]
                port = peer.split(':')[1]
                self.peers.append((ip,port))
            else:
                port = self.port
                self.peers.append((peer,port))

        return (self.port, self.folder, self.p_prob, self.q_prob,self.peers, self.passwd)

    def load_password(self):
        pwd = getpass.getpass("Introduce user password: ")
        print "The password introduced is: ", pwd
        return pwd
