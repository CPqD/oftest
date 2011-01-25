'''
Created on Jan 24, 2011

@author: capveg
'''
import logging

from oftest import cstruct as ofp
from oftest import ofutils


def validate_flow_mod(switch, flow_mod):
    """ Sanity check the flow_mods match and actions
    
    Make sure that all of the actions are valid and make
    sense given this match.
    
    @note:  this function is intentionally somewhat naive.  It does
    not consider the current state of the flow_tables or switch config
    before deciding a flow_mod is valid.  This behavior is conformant to
    the spec, per 5.5 in the spec 
    
    @return:  None if no error; else an ofp_error instance to send back to the
      controller 
    """
    logger = logging.getLogger("validate")

    err = None
    for instruction in flow_mod.instructions:
        t = instruction.__class__.__name__
        cmd = "err = _validate_" + \
                "%s(instruction, switch, flow_mod, logger)" % t
        try:
            exec cmd
            if err:
                return err
        except Exception, e:
            logger.error(
                "No validation test for instruction %s:: failed cmd '%s'::%s"  %
                (t, cmd, str(e)))
    return None
            
##### instructions 

def _validate_instruction_apply_actions(instruction, switch, flow_mod, logger):
    """ Sanity check apply actions
    """
    err = None
    for action in instruction.actions: 
        t = action.__class__.__name__
        cmd = "err = _validate_" + \
                "%s(action, switch, flow_mod, logger)" % t
        try:
            exec cmd
            if err:
                return err
        except:
            logger.error(
                "No validation test for action %s:: failed cmd '%s'"  %
                (t, cmd))       
    return None

def _validate_instruction_goto_table(instruction, switch, flow_mod, logger):
    table_id = instruction.table_id
    if table_id >= 0 and table_id < switch.pipeline.n_tables :
        return None
    else:
        return ofutils.of_error_msg_make(ofp.OFPET_BAD_ACTION,
                                         ofp.OFPBAC_BAD_ARGUMENT, 
                                         flow_mod)

def _validate_instruction_write_actions(instruction, switch, flow_mod, logger):
    pass
def _validate_instruction_write_metadata(instruction, switch, flow_mod, logger):
    pass
def _validate_instruction_experimenter(instruction, switch, flow_mod, logger):
    pass
def _validate_instruction_clear_actions(instruction, switch, flow_mod, logger):
    pass



##### Actions

def _validate_action_output(action, switch, flow_mod, logger):
    try: 
        if (action.port >= ofp.OFPP_MAX or 
                    switch.ports[action.port] is not None):
            return None         # port is valid
    except KeyError:
        logger.error("Got KeyError when checking port %x" % action.port )
        pass                    # just fall through
    return ofutils.of_error_msg_make(ofp.OFPET_BAD_ACTION, 
                                     ofp.OFPBAC_BAD_OUT_PORT, 
                                     flow_mod)
        
def _validate_action_pop_vlan(action, switch, flow_mod, logger):
    pass
def _validate_action_set_dl_dst(action, switch, flow_mod, logger):
    pass
def _validate_action_set_dl_src(action, switch, flow_mod, logger):
    pass
def _validate_action_set_nw_dst(action, switch, flow_mod, logger):
    pass
def _validate_action_set_nw_src(action, switch, flow_mod, logger):
    pass
def _validate_action_set_nw_tos(action, switch, flow_mod, logger):
    pass
def _validate_action_set_tp_dst(action, switch, flow_mod, logger):
    pass
def _validate_action_set_tp_src(action, switch, flow_mod, logger):
    pass
def _validate_action_set_vlan_vid(action, switch, flow_mod, logger):
    pass
