#!/usr/lib/python
#
#Copyright [2016] [SnapRoute Inc]
#
#Licensed under the Apache License, Version 2.0 (the "License");
#you may not use this file except in compliance with the License.
#You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing, software
#       distributed under the License is distributed on an "AS IS" BASIS,
#       WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#       See the License for the specific language governing permissions and
#       limitations under the License.
#
# _______  __       __________   ___      _______.____    __    ____  __  .___________.  ______  __    __
# |   ____||  |     |   ____\  \ /  /     /       |\   \  /  \  /   / |  | |           | /      ||  |  |  |
# |  |__   |  |     |  |__   \  V  /     |   (----` \   \/    \/   /  |  | `---|  |----`|  ,----'|  |__|  |
# |   __|  |  |     |   __|   >   <       \   \      \            /   |  |     |  |     |  |     |   __   |
# |  |     |  `----.|  |____ /  .  \  .----)   |      \    /\    /    |  |     |  |     |  `----.|  |  |  |
# |__|     |_______||_______/__/ \__\ |_______/        \__/  \__/     |__|     |__|      \______||__|  |__|
#
# Main routine for the cli, will contain root node functionality within the cli tree
# Will be the container for the reference to the flexSdk and flexPrint, as well
# as holds the master model and schema for the cli.   The Cli utilizes a class cmdln.py which
# was built as a wrapper above the common cmd class as part of the standard python library as of 2.7
#

import sys, getopt, socket, os
import jsonref
import cmdln
import readline
import rlcompleter
import glob
import shutil
from collections import Counter
from itertools import izip_longest
from optparse import OptionParser
from jsonschema import Draft4Validator
#from snap_global import Global_CmdLine
from snap_config import ConfigCmd
from snap_show import ShowCmd
from commonCmdLine import CommonCmdLine, USING_READLINE
from flexswitchV2 import FlexSwitch
from flexprint import FlexPrint
from sets import Set

class CmdFunc(object):
    def __init__(self, origfuncname, func):
        self.name = origfuncname
        self.func = func

        # lets save off the function attributes to the class
        # in case someone like cmdln access it (which it does)
        x = dir(func)
        y = dir(self.__class__)
        z = Set(x).difference(y)
        for attr in z:
            setattr(self, attr, func.__getattribute__(attr))

    # allow class to be called as a method
    def __call__(self, *args, **kwargs):
        self.func(*args, **kwargs)


class CmdLine(cmdln.Cmdln, CommonCmdLine):
    """
    Help may be requested at any point in a command by entering
    a question mark '?'.  If nothing matches, the help list will
    be empty and you must backup until entering a '?' shows the
    available options.
    Two styles of help are provided:
    1. Full help is available when you are ready to enter a
       command argument (e.g. 'show ?') and describes each possible
       argument.
    2. Partial help is provided when an abbreviated argument is entered
       and you want to know what arguments match the input
       (e.g. 'show pr?'.)
    """
    # name of schema and model
    name = 'base.json'
    objname = 'base'
    def __init__(self, switch_ip, model_path, schema_path):
        self.start = True

        cmdln.Cmdln.__init__(self)
        self.privilege = False
        self.tmp_remove_priveledge = None
        self.sdk = FlexSwitch(switch_ip, 8080)
        self.sdkshow = FlexPrint(switch_ip, 8080)

        # this must be called after sdk setting as the common init is valididating
        # the model and some info needs to be gathered from system to populate the
        # cli accordingly
        CommonCmdLine.__init__(self, None, switch_ip, schema_path, model_path, self.name)

        # lets make sure the model is correct
        valid = self.validateSchemaAndModel()

        if not valid:
            sys.stdout.write("schema and model mismatch")
            sys.exit(0)

        # this loop will setup each of the cliname commands for this model level
        for subcmds, cmd in self.model["commands"].iteritems():
            # handle the links
            if 'subcmd' in subcmds:
                try:
                    for k,v in cmd.iteritems():
                        cmdname = self.getCliName(v)
                        if '-' in cmdname:
                            sys.stdout.write("MODEL conflict invalid character '-' in name %s not supported by CLI" %(cmdname,))
                            self.do_exit([])
                            cmdname = cmdname.replace('-', '_')

                        funcname = "do_" + cmdname
                        setattr(self.__class__, funcname, CmdFunc(funcname, self.__getattribute__("_cmd_%s" %(k,))))
                        if hasattr(self.__class__, "_cmd_complete_%s" %(k,)):
                            setattr(self.__class__, "complete_" + cmdname, self.__getattribute__("_cmd_complete_%s" %(k,)))
                except Exception as e:
                    sys.stdout.write("EXCEPTION RAISED on setting do_: %s\n" %(e,))
            else:
                # handle commands when are not links
                try:
                    cmdname = self.getCliName(self.model["commands"][subcmds])
                    if '-' in cmdname:
                        sys.stdout.write("MODEL conflict invalid character '-' in name %s not supported by CLI" %(cmdname,))
                        self.do_exit([])
                        cmdname = cmdname.replace('-', '_')

                    funcname = "do_" + cmdname
                    setattr(self.__class__, funcname, CmdFunc(funcname, self.__getattribute__("_cmd_%s" %(subcmds,))))
                except Exception as e:
                        sys.stdout.write("EXCEPTION RAISED on setting do_: %s\n" %(e,))


        self.setBanner(switch_ip)

    def setBanner(self, switch_ip):

        self.intro = "FlexSwitch Console Version 1.0, Connected to: " + self.switch_name
        self.intro += "\nUsing %s style cli\n" %(self.model["style"],)

    def do_show_cli(self, arv):

        def submcmd_walk(subcmd):
            if type(subcmd) in (dict, jsonref.JsonRef):
                for k, v in subcmd.iteritems():
                    currcmdline = ''
                    if type(v) in (dict, jsonref.JsonRef):
                        if 'cliname' in v:
                            currcmdline += ' ' + v['cliname']
                        if 'commands' in v:
                            for kk, vv in v['commands'].iteritems():
                                if 'subcmd' in kk:
                                    for x in  submcmd_walk(vv):
                                        newcmdline = currcmdline + x
                                        yield newcmdline
                                elif type(vv) in (dict, jsonref.JsonRef):
                                    for kkk, vvv in vv.iteritems():
                                        if 'cliname' in kkk:
                                            newcmdline = currcmdline + vvv
                                            yield newcmdline
                        else:
                            # reached the attributes
                            for kk, vv in v.iteritems():
                                if 'cliname' in vv:
                                    newcmdline = currcmdline + ' ' + vv['cliname']
                                    yield newcmdline
            yield ''

        cmdList = []
        for k, v in self.model.iteritems():
            if "commands" == k:
                for kk, vv in v.iteritems():
                    cmdline = ''
                    if 'subcmd' in kk:
                        #traverse the commands
                        for x in submcmd_walk(vv):
                            cmdline = x
                            if cmdline not in cmdList:
                                cmdList.append(cmdline)
                    else:
                        for kkk, vvv in vv.iteritems():
                            if 'cliname' in kkk:
                                cmdline = vvv
                                if cmdline not in cmdList:
                                    cmdList.append(cmdline)
        for x in cmdList:
            print x


    def replace_cli_name(self, name, newname):
        def submcmd_walk(name, newname, subcmd):
            if type(subcmd) in (dict, jsonref.JsonRef):
                for k, v in subcmd.iteritems():
                    if type(v) in (dict, jsonref.JsonRef):
                        if 'cliname' in v and v['cliname'] == name:
                            v['cliname'] = newname
                        if 'commands' in v:
                            for kk, vv in v['commands'].iteritems():
                                if 'subcmd' in kk:
                                    submcmd_walk(name, newname, vv)
                                elif type(vv) in (dict, jsonref.JsonRef):
                                    for kkk, vvv in vv.iteritems():
                                        if 'cliname' in kkk and vvv == name:
                                            vv[kkk] = name

                        else:
                            # reached the attributes
                            for kk, vv in v.iteritems():
                                if 'cliname' in vv and vv['cliname'] == name:
                                    vv['cliname'] = newname

        for k, v in self.model.iteritems():
            if "commands" == k:
                if type(v) in (dict, jsonref.JsonRef):
                    for kk, vv in v.iteritems():
                        if 'subcmd' in kk:
                            #traverse the commands
                            submcmd_walk(name, newname, vv)
                        elif type(vv) in (dict, jsonref.JsonRef):
                            for kkk, vvv in vv.iteritems():
                                if 'cliname' in kkk and vvv == name:
                                    vv[kkk] = newname

    def validateSchemaAndModel(self):

        def detect_port_prefix(strings):
            threshold = len(strings)
            prefix = []
            prefixes = []
            for chars in izip_longest(*strings, fillvalue=''):
                char, count = Counter(chars).most_common(1)[0]
                if count == 1:
                    break
                elif count < threshold:
                    if prefix:
                        prefixes.append((''.join(prefix), threshold))
                    threshold = count
                prefix.append(char)
            if prefix:
                prefixes.append((''.join(prefix), threshold))
            #print prefixes
            #print max([x[1] for x in prefixes])
            maxprefix = [y[0] for y in prefixes if y[1] == max([x[1] for x in prefixes])][0]
            return maxprefix

        if self.model is None or self.schema is None:
            sys.exit(2)
        else:
            try:
                try:
                    self.switch_name = socket.gethostbyname(self.switch_ip)
                except socket.gaierror:
                    self.switch_name = self.switch_ip

                # update to add the prompt prefix
                self.model["prompt-prefix"] = self.switch_name
                try:
                    sdk = self.getSdk()
                    ports = sdk.getAllPorts()
                    if ports:
                        port_prefix = detect_port_prefix([p['Object']['IntfRef'] for p in ports])
                        self.replace_cli_name('ethernet', port_prefix)

                except Exception as e:
                    sys.stdout.write("Failed to find port prefix exiting CLI, is switch %s accessable?\n" %(self.switch_name))
                    self.do_exit([])

                #with open(self.modelpath, 'w') as f:
                #    jsonref.dump(self.model, f, indent=2)
                #self.setModel()
                self.setPrompt()

                # lets validate the model against the json schema
                Draft4Validator(self.schema).validate(self.model)

            except Exception as e:
                print e
                return False
        return True

    def setPrompt(self, ):

        # set the prompt
        self.baseprompt = self.model["prompt-prefix"] + self.model["prompt"]
        self.prompt = self.model["prompt-prefix"] + self.model["prompt"]

    def cmdloop(self, intro=None):
        try:
            if self.start:
                self.start = False
                cmdln.Cmdln.cmdloop(self, intro=self.intro)
            else:
                cmdln.Cmdln.cmdloop(self, intro="")
        except KeyboardInterrupt:
            self.intro = '\n'
            self.cmdloop()


    def emptyline(self):
        pass

    @cmdln.alias("en", "ena")
    # match for schema cmd object
    def _cmd_privilege(self, arg):
        self.privilege = True
        submodelList = self.getSubCommand("privilege", self.model["commands"])
        subschemaList = self.getSubCommand("privilege", self.schema["properties"]["commands"]["properties"])
        if submodelList and subschemaList and len(submodelList) == 1:
            for submodel, subschema in zip(submodelList, subschemaList):
                self.prompt = self.prompt[:-1] + self.getPrompt(submodel, subschema)
                self.baseprompt = self.prompt
                self.currentcmd = self.lastcmd

        if self.stop:
            self.cmdloop()

    def xdo_help(self, arg):
        doc_strings = [ (i[3:], getattr(self, i).__doc__)
            for i in dir(self) if i.startswith('do_') ]
        doc_strings = [ '  %s\t%s\n' % (i, j)
            for i, j in doc_strings if j is not None ]
        sys.stdout.write('%s\n' % ''.join(doc_strings))

    @cmdln.alias("conf t", "configure t", "configure term", "conf term", "configure terminal", "config t")
    # match for schema cmd object
    def _cmd_config(self, args):
        " Global configuration mode "
        if self.privilege is False:
            return

        if len(args) > 1:
            self.display_help(args)
            return

        functionNameAsString = sys._getframe().f_code.co_name
        name = functionNameAsString.split("_")[-1]
        # get the submodule to be passed into config
        #schemaname = self.getSchemaCommandNameFromCliName(name, self.model)
        submodelList = self.getSubCommand(name, self.model["commands"])
        subschemaList = self.getSubCommand(name, self.schema["properties"]["commands"]["properties"])
        # there should only be one config entry
        if submodelList and subschemaList and len(submodelList) == 1:
            for submodel, subschema in zip(submodelList, subschemaList):
                configprompt = self.getPrompt(submodel[name], subschema[name])
                # setup the prompt accordingly
                self.prompt = self.prompt[:-1] + configprompt + self.prompt[-1]
                # stop the command loop for config as we will be running a new cmd loop
                cmdln.Cmdln.stop = True
                # save off the current command
                prevcmd = self.currentcmd
                self.currentcmd = self.lastcmd

                c = ConfigCmd("config", self, name, self.prompt, submodel, subschema)
                c.cmdloop()
                # clear the command if we return
                self.currentcmd = prevcmd
                # return prompt to the base of this class
                self.prompt = self.baseprompt
                if self.stop:
                    self.cmdloop()

    def _cmd_complete_show(self, text, line, begidx, endidx):
        #sys.stdout.write("\n%s line: %s text: %s %s\n" %(self.objname, line, text, not text))
        # remove spacing/tab
        mline = [x for x in line.split(' ') if x != '']
        mlineLength = len(mline)
        #sys.stdout.write("complete \ncommand %s objname %s\n\n" %(mline, self.objname))

        functionNameAsString = sys._getframe().f_code.co_name
        name = functionNameAsString.split("_")[-1]

        submodelList = self.getSubCommand(name, self.model["commands"])
        subschemaList = self.getSubCommand(name, self.schema["properties"]["commands"]["properties"], self.model["commands"])
        subcommands = self.getchildrencmds(mline[0], submodelList[0], subschemaList[0])
        if mlineLength > 0:
            try:
                for i in range(1, mlineLength):
                    for submodel, subschema in zip(submodelList, subschemaList):
                        schemaname = self.getSchemaCommandNameFromCliName(mline[i-1], submodel)
                        submodelList = self.getSubCommand(mline[i], submodel[schemaname]["commands"])
                        if submodelList:
                            subschemaList = self.getSubCommand(mline[i], subschema[schemaname]["properties"]["commands"]["properties"], submodel[schemaname]["commands"])
                            for subsubmodel, subsubschema in zip(submodelList, subschemaList):
                                #valueexpected = self.isValueExpected(mline[i], subsubmodel, subsubschema)
                                # we want to keep looping untill there are no more value commands
                                #if valueexpected and mlineLength-1 == i:
                                subcommands = self.getchildrencmds(mline[i], subsubmodel, subsubschema)


            except Exception:
                pass

        # todo should look next command so that this is not 'sort of hard coded'
        # todo should to a getall at this point to get all of the interface types once a type is found
        #sys.stdout.write("3: subcommands: %s\n\n" %(subcommands,))

        # lets remove any duplicates
        returncommands = list(Set(subcommands).difference(mline))

        if len(text) == 0 and len(returncommands) == len(subcommands):
            #sys.stdout.write("just before return %s" %(returncommands))
            return returncommands
        #elif len(text) == 0:
        #    # todo get all values ?
        #    pass
        # lets only get commands which are a partial of what was entered
        returncommands = [k for k in returncommands if k.startswith(text)]

        return returncommands

    def display_show_help(self, mline):
        mlineLength = len(mline)
        submodelList = self.getSubCommand("show", self.model["commands"])
        subschemaList = self.getSubCommand("show", self.schema["properties"]["commands"]["properties"], self.model["commands"])
        for submodel, subschema in zip(submodelList, subschemaList):
            c = ShowCmd(self, submodel, subschema)
            c.display_help(mline[1:])


    def _cmd_show(self, argv):
        " Show running system information "
        mline = argv
        if mline[-1] in ('help', '?'):
            self.display_show_help(mline)
            return argv

        functionNameAsString = sys._getframe().f_code.co_name
        name = functionNameAsString.split("_")[-1]
        mlineLength = len(mline)
        submodelList = self.getSubCommand(name, self.model["commands"])
        subschemaList = self.getSubCommand(name, self.schema["properties"]["commands"]["properties"], self.model["commands"])
        if mlineLength > 0:
            try:

                for i in range(1, mlineLength):
                    for submodel, subschema in zip(submodelList, subschemaList):
                        schemaname = self.getSchemaCommandNameFromCliName(mline[i-1], submodel)
                        submodelList = self.getSubCommand(mline[i], submodel[schemaname]["commands"])
                        if submodelList:
                            subschemaList = self.getSubCommand(mline[i], subschema[schemaname]["properties"]["commands"]["properties"], submodel[schemaname]["commands"])
                            for subsubmodel, subsubschema in zip(submodelList, subschemaList):
                                (valueexpected, objname, keys, help) = self.isValueExpected(mline[i], subsubmodel, subsubschema)
                                # we want to keep looping untill there are no more value commands
                                if valueexpected and mlineLength-1 == i:
                                    self.currentcmd = self.lastcmd
                                    c = ShowCmd(self, subsubmodel, subsubschema)
                                    c.show(mline, all=(i == mlineLength-1))
                                    self.currentcmd = []


            except Exception:
                pass

        if self.stop:
            self.cmdloop()

    def do_exit(self, args):
        " Quiting FlexSwitch CLI"
        #subcmd = self.getSubCommand("privilege", self.model["commands"])
        if self.privilege:
            self.privilege = False
            #docmd = 'do_%s' %(subcmd['cliname'])
            #setattr(self.__class__, docmd, self.tmp_remove_priveledge)
            sys.stdout.write('Exiting Privilege mode\n')
            self.setPrompt()
            self.cmdloop()

        else:
            sys.stdout.write('Quiting Shell\n')
            sys.exit(0)

class PrepareModel(object):
    def __init__(self, cli_model_path, cli_schema_path):
        # path location on the local drive where the cli model is located
        self.model_path = cli_model_path
        # path location on the local drive where the cli schema is located
        self.schema_path = cli_schema_path
        # path where model ref's will live
        self.ref_model_path = '/tmp/snaproute/cli/model/' + cli_model_path.split('/')[-2] + '/'
        # path where schema ref's will live
        self.ref_schema_path = '/tmp/snaproute/cli/schema/'

    def Prepare(self):
        # create the directories if they don't already exist
        # if it exists function will remove existing files
        self.mkdir_p(self.ref_model_path)
        self.mkdir_p(self.ref_schema_path)

        self.copy_json_to_new_path(self.model_path, self.ref_model_path)
        self.copy_json_to_new_path(self.schema_path, self.ref_schema_path)

    def mkdir_p(self, path):

        # lets clean the directory if it exists in case other models exist
        try:
            shutil.rmtree(path)
        except Exception:
            pass

        if not os.access(path, os.F_OK):
            os.makedirs(path)

    def copy_json_to_new_path(self, oldpath, newpath):

        for filename in glob.glob(os.path.join(oldpath, '*.json')):
            #sys.stdout.write("copying file:%s to %s\n" %(filename, newpath))
            try:
                shutil.copy(filename, newpath)
            except IOError:
                pass



# *** MAIN LOOP ***
if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option("-s", "--switch", action="store", dest="switch_ip", type="string",
                      help="Switch IP to run the cli against", default= '127.0.0.1')
    parser.add_option("-m", "--model", action="store",type="string",
                      dest="cli_model_path",
                      help="Path to the cli model to be used",
                      default= './models/cisco/')
    parser.add_option("-j", "--jschema", action="store",type="string",
                      dest="cli_schema_path",
                      help="Path to the cli model to be used",
                      default='./schema/')
    (options, args) = parser.parse_args()

    switch_ip='127.0.0.1'
    switch_ip = options.switch_ip
    cli_model_path = options.cli_model_path
    cli_schema_path = options.cli_schema_path

    # lets make /tmp/snaproute/cli/ directory if it does not exist
    # if it does exist lets clean the directory
    # lets move all the json schema and model to a temporary
    # directory structure so that the jsonref can properly
    # parse the references
    # /tmp/snaproute/cli/models
    # /tmp/snaproute/cli/schema
    x = PrepareModel(cli_model_path, cli_schema_path)
    x.Prepare()


    cmdLine = CmdLine(switch_ip, cli_model_path, cli_schema_path, )
    #sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #result = sock.connect_ex((switch_ip,8080))
    result = True
    if result:
        cmdLine.cmdloop()
    else:
        print "FlexSwitch not reachable, Please ensure daemon is up."
        sys.exit(2)

