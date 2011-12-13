# -*- test-case-name: vumi.workers.ttc.tests.test_ttc -*-

from twisted.python import log
from twisted.internet.defer import inlineCallbacks
from twisted.enterprise import adbapi
from twisted.internet import task

from twistar.dbobject import DBObject
from twistar.registry import Registry

import pymongo

from datetime import datetime, time, date, timedelta

from vumi.application import ApplicationWorker
from vumi.message import Message, TransportUserMessage
from vumi.application import SessionManager

#from vumi.database.base import setup_db, get_db, close_db, UglyModel

#class ParticipantModel(UglyModel):
    #TABLE_NAME = 'participant_items'
    #fields = (
        #('id', 'SERIAL PRIMARY KEY'),
        #('phone_number','int8 UNIQUE NOT NULL'),
        #)
    #indexes = ('phone_number',)
    
    #@classmethod
    #def get_items(cls, txn):
        #items = cls.run_select(txn,'')
        #if items:
            #items[:] = [cls(txn,*item) for item in items]
            #return items
            ##return cls(txn, *items[0])
        #return None
    
    #@classmethod
    #def create_item(cls, txn, number):
        #params = {'phone_number': number}
        #txn.execute(cls.insert_values_query(**params),params)
        #txn.execute("SELECT lastval()")
        #return txn.fetchone()[0]

#Models#
#CREATE TABLE dialogues (id SERIAL PRIMARY KEY, name VARCHAR(50),type VARCHAR(20)) 
#CREATE TABLE interactions (id SERIAL PRIMARY KEY, name VARCHAR, content VARCHAR(50), schedule_type VARCHAR(30), dialogue_id INT)
#CREATE TABLE schedules (id SERIAL PRIMARY KEY, type VARCHAR(30), interaction_id INT)
#CREATE TABLE participants (id SERIAL PRIMARY KEY, phone INT, name VARCHAR(50))

#Model Relations#
#class Dialogue(DBObject):
    #HASMANY=['interactions']
    
#class Interaction(DBObject):
    #BELONGSTO=['dialogue']

#class Schedule(DBObject):
    #BELONGSTO=['interaction']

#class Participant(DBObject):
    #pass

#class SentMessage(DBObject):
    #HASMANY=['participants']

#Registry.register(Dialogue, Interaction, Participant, SentMessage)

class TtcGenericWorker(ApplicationWorker):
    
    def databaseAccessSuccess(self, result):
        log.msg("Databasee Access Succeed %s" %result)
    
    def databaseAccessFailure(self, failure):
        log.msg("Databasee Access Succeed %s" % failure)
    
    
    @inlineCallbacks
    def startWorker(self):
        super(TtcGenericWorker, self).startWorker()
        self.control_consumer = yield self.consume(
            '%(transport_name)s.control' % self.config,
            self.consume_control,
            message_class=Message)
    
        #config
        self.transport_name = self.config.get('transport_name')
        self.transport_type = 'sms'

        #some basic local recording
        self.record = []

        # Try to access database with Ugly model
        #self.setup_db = setup_db(ParticipantModel)
        #self.db = setup_db('test', database='test',
        #         user='vumi',
        #         password='vumi',
        #         host='localhost')
        #self.db.runQuery('SELECT 1')
    
        # Try to Access Redis
        #self.redis = SessionManager(db=0, prefix="test")
        
        #self.sender = task.LoopingCall(lambda: self.send_scheduled())
        #self.sender.start(10.0)
        
        # Try to Access relational database with twistar
        #Registry.DBPOOL = adbapi.ConnectionPool('psycopg2', "dbname=test host=localhost user=vumi password=vumi")
        #yield Registry.DBPOOL.runQuery("SELECT 1").addCallback(self.databaseAccessSuccess)
    
        # Try to Access Document database with pymongo
        connection = pymongo.Connection("localhost",27017)
        self.db = connection.test
    
    def consume_user_message(self, message):
        log.msg("User message: %s" % message['content'])
    
    #@inlineCallbacks
    def consume_control(self, message):
        log.msg("Control message!")
        #data = message.payload['data']
        self.record.append(('config',message))
        if (message.get('program')):
            log.msg("received a program")
            program = message.get('program')
            log.msg("Start the program %s" % program.get('name'))

            #MongoDB#
            programs = self.db.programs
            programs.insert(program)
            
            #Redis#
            #self.redis.create_session("program")
            #self.redis.save_session("program", program)
            #session = self.redis.load_session("program")
            #log.msg("Message stored and retrieved %s" % session.get('name'))
            
            #UglyModel#
            #self.db.runInteraction(ParticipantModel.create_item,68473)        
            #name = program.get('name')
            #group = program.get('group',{})
            #number = group.get('number')
            #log.msg("Control message %s to be add %s" % (number,name))
      
            #Twistar#                
            #def failure(error):
                #log.msg("failure while saving %s" %error)
                
            #if(program.get('dialogues')):
                #yield self.saveDialoguesDB(program.get('dialogues'))
            #if(program.get('participants')):
                #yield self.saveParticipantsDB(program.get('participants'))
        
        elif (message.get('participants')):
            program = self.db.programs.find_one()
            program['participants'] = message.get('participants')
            self.db.programs.save(program)
            #self.record.append(('config',message))
            #yield self.saveParticipantsDB(message.get("participants"))

    
    def dispatch_event(self, message):
        log.msg("Event message!")
    
    #TODO: fire error feedback if the dialogue do not exit anymore
    #TODO: if dialogue is deleted, need to remove the scheduled message (or they are also canceled if cannot find the dialogue)
    @inlineCallbacks
    def send_scheduled(self):
        log.msg('Sending Scheduled message start')
        toSends = self.db.schedules.find(spec={"datetime":{"$lt":datetime.now().isoformat()}},sort=[("datetime",1)])
        for toSend in toSends:
            self.db.schedules.remove({"_id":toSend.get('_id')})
            yield self.transport_publisher.publish_message(
                TransportUserMessage(**{'from_addr':'',
                                      'to_addr':toSend.get('participant_phone'),
                                      'transport_name':self.transport_name,
                                      'transport_type':self.transport_type,
                                      'transport_metadata':''
                                    }));
                        
    #TODO: manage multiple timezone
    #TODO: manage other schedule type
    #TODO: decide which id should be in an schedule object
    def schedule_participant_dialogue(self, participant, dialogue):
        #schedules = self.db.schedules
        previousDateTime = None
        schedules = []
        for interaction in dialogue.get('interactions'):
            schedule = {"datetime":None, 
                        "participant_phone": participant.get('phone'), 
                        "dialogue_name":dialogue.get("name"), 
                        "interaction_name":interaction.get("name")}
            if (dialogue.get('type')=="sequential"):
                if (interaction.get('schedule_type')=="immediately"):
                    currentDateTime = datetime.now()
                if (interaction.get('schedule_type')=="wait"):
                    currentDateTime = previdousDateTime + timedelta(minutes=10)
                schedule["datetime"] = currentDateTime.isoformat()
            schedules.append(schedule)
            previdousDateTime = currentDateTime
        return schedules
            #schedules.save(schedule)
    
    #Deprecated
    @inlineCallbacks
    def saveParticipantsDB(self, participants):
        log.msg("received a list of phone")
        for participant in participants:
            oParticipant = yield Participant.find(where=['phone = ?', participant.get('phone')],limit=1)
            if (oParticipant == None):
                oParticipant = yield Participant(phone=participant.get('phone'),
                                           name=participant.get('name')).save()
            else:
                #if (participant.get('name')):
                oParticipant.name = participant.get('name')
                yield oParticipant.save()
    
    #Deprecated
    @inlineCallbacks
    def saveDialoguesDB(self, dialogues):
        for dialogue in dialogues:
            #oDialogue = yield Dialogue(name=dialogue.get('name'),type=dialogue.get('type')).save().addCallback(onDialogueSave,dialogue.get('interactions')).addErrback(failure)
            oDialogue = yield Dialogue.find(where=['name = ?',dialogue.get('name')], limit=1)
            if (oDialogue==None):
                oDialogue = yield Dialogue(name=dialogue.get('name'),type=dialogue.get('type')).save().addErrback(failure)
            else:
                oDialogue.name = dialogue.get('name')
                yield oDialogue.save()
            for interaction in dialogue.get('interactions'):
                if interaction.get('type')== "announcement":
                    oInteraction = yield Interaction.find(where=['name = ?',interaction.get('name')], limit=1)
                    if (oInteraction==None):
                        oInteraction = yield Interaction(content=interaction.get('content'),
                                                         name=interaction.get('name'),
                                                         schedule_type=interaction.get('schedule_type'), 
                                                         dialogue_id=oDialogue.id).save().addErrback(failure)
                    else:
                        oInteraction.content = interaction.get('content')
                        oInteraction.name = interaction.get('name')
                        oInteraction.schedule_type=interaction.get('schedule_type')
                        yield oInteraction.save()
                    #yield Schedule(type=interaction.get("schedule_type"),
                                   #interaction_id=oInteraction.id).save()