import os
import time
import argparse
import shutil
import threading
import simplejson as json
from flexswitchV2 import FlexSwitch

gObjectsInfo =  {}

class ConfigObjList (object):
    def __init__ (self, swtch, name, currentList, newList):
        self.name = name
        self.swtch = swtch
        self.current = currentList
        self.desire  = newList
        self.attrInfo = gObjectsInfo[name]
        self.currentDict = self.convertObjListToDict(currentList)
        self.desiredDict = self.convertObjListToDict(newList)

    def convertObjListToDict (self, objList):
        retDict = {}
        for item in objList:
            keyStr = ''
            for attrName, attrInfo  in self.attrInfo.iteritems():
                if attrInfo['isKey'] == True:
                    keyStr = keyStr + attrName+str(item[attrName])
            retDict[keyStr] = item
        return retDict

    def getObjKeyFromObj(self, objDict):
        retDict = {}
        for attrName , attrVal in objDict.iteritems:
            if attrName in self.attrInfo:
                if self.attrInfo[attrName]['isKey'] == 'true':
                    retDict[attrName] = attrVal
        return retDict

    def applyConfig (self):
        for key, item in self.desiredDict.iteritems():
            if key not in self.currentDict:
                self.createObj(self.desiredDict[key])
            else:
                self.updateObj(self.desiredDict[key])

        for key, item in self.currentDict.iteritems():
            if key not in self.desiredDict:
                self.deleteObj(self.desiredDict[key])

    def createObj (self, objData):
        methodName = 'create' + self.name
        method =  getattr(self.swtch, methodName, None)
        if method :
            method(**objData)
        print 'Creating Object %s' %(self.name)

    def deleteObj (self, objDict):
        methodName = 'delete' + self.name
        method =  getattr(self.swtch, methodName, None)
        if method :
            keys = self.getObjKeyFromObj(objDict)
            method(**keys)
        print 'Deleting Object %s' %(self.name)

    def updateObj (self, objData):
        methodName = 'update' + self.name
        method =  getattr(self.swtch, methodName, None)
        if method :
            method(**objData)
        print 'Updating object %s' %(self.name)

class ConfigMonitor (object) :
    def __init__ (self, ip, port, cfgDir, pollFreq=5) :
        global gObjectsInfo
        self.cfgDir = cfgDir
        self.runningCfg = cfgDir + '/runningConfig.json'
        self.desiredCfg = cfgDir + '/desiredConfig.json'
        self.oldCfg     = cfgDir + '/oldConfig.json'
        self.ip = ip
        self.port = port
        self.objects =  {}
        self.swtch = FlexSwitch(self.ip, self.port)
        self.currentConfig = {}
        self.cfgObjOrder = []
        self.pollFreq = pollFreq

        with open('modelInfo/genObjectConfig.json') as objInfoFile:    
            self.objects = json.load(objInfoFile)

        for obj in self.objects.keys():
            attrInfoFile = 'modelInfo/%sMembers.json' %(obj)
            with open(attrInfoFile) as hdl : 
                gObjectsInfo[obj] = json.load(hdl)
            
        with open('modelInfo/configOrder.json') as orderInfoFile:    
            orderInfo = json.load(orderInfoFile)
        self.cfgObjOrder = orderInfo['Order']
        self.saveConfig()

    def deleteConfig (self) :
        pass

    def applyRunningConfig (self):
        self.applyConfig(self.currentConfig)

    def applyDesiredConfig(self, configFile=None):
        if configFile == None:
            configFile = self.desiredCfg
        with open(configFile) as desired: 
            desiredCfg = json.load(desired)
        self.applyConfig (desiredCfg)

    def applyConfig (self, config) :
        for obj in self.cfgObjOrder:
            if config.has_key(obj):
                objList = ConfigObjList (self.swtch, obj, self.currentConfig[obj], config[obj])
                objList.applyConfig()

    def saveConfig(self) :
        for objName, objInfo  in self.objects.iteritems ():
            if 'w' in objInfo['access'] :
                methodName = 'getAll'+objName+'s'
                method =  getattr(self.swtch, methodName, None)
                if method :
                    cfgList = method()
                    if cfgList != None and len(cfgList) :
                        self.currentConfig [objName] = []
                        for cfg in cfgList: 
                            currentObj = json.loads(json.dumps(cfg['Object']))
                            self.currentConfig[objName].append(currentObj)

        with open(self.runningCfg, 'w') as runningCfg:
            json.dump(self.currentConfig, runningCfg, indent=4, separators=(',', ': '))

        if not os.path.isfile(self.desiredCfg):
            print 'Current Config %s New Config %s ' %(self.runningCfg, self.desiredCfg)
            shutil.copyfile(self.runningCfg, self.desiredCfg)
        self.modifiedTime = os.stat(self.desiredCfg).st_mtime
            

    def pollForConfigChange(self):
        poller = threading.Timer(self.pollFreq, self.pollForConfigChange)
        newTime = os.stat(self.desiredCfg).st_mtime
        print '## Checking Config %s. Old Time %s New Time %s' %(self.desiredCfg, self.modifiedTime, newTime)
        if newTime > self.modifiedTime:
            self.modifiedTime = newTime
            self.applyDesiredConfig()
        poller.start()
            
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='FlexSwitch Configuration monitor')
    parser.add_argument('--cfgDir',
                        type=str, 
                        dest='cfgDir',
                        action='store',
                        nargs='?',
                        default='/opt/flexswitch/',
                        help='Location of configuration file')

    parser.add_argument('--ip',
                        type=str, 
                        dest='ip',
                        action='store',
                        nargs='?',
                        default='localhost',
                        help='Ip Address of the node')

    parser.add_argument('--port',
                        type=str, 
                        dest='port',
                        action='store',
                        nargs='?',
                        default='8080',
                        help='Port')

    parser.add_argument('--poll',
                        type=str, 
                        dest='poll',
                        action='store',
                        nargs='?',
                        default='30',
                        help='Polling interval')
    args = parser.parse_args()
    monitor = ConfigMonitor (args.ip, args.port, args.cfgDir, int(args.poll))
    monitor.saveConfig()
    #monitor.applyDesiredConfig('tmp/desiredConfig.json')
    monitor.pollForConfigChange()
    while True:
        time.sleep(1)
    #monitor.applyRunningConfig()
