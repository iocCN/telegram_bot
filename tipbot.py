#!/usr/bin/python
# coding=utf-8

import logging

import emoji

from telegram import ParseMode, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler
from telegram.ext import Updater, CallbackContext, filters

from HelperFunctions import *
from rpc import CoinRPC, Wrapper as RPCWrapper

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

config = load_file_json("config.json")
_lang = "en"  # ToDo: Per-user language
strings = Strings("strings.json")
_paused = False
_testnet = True
_spam_filter = AntiSpamFilter(config["spam_filter"][0], config["spam_filter"][1])
_rain_queues = {
    "-1": [("0", "@username", "Name")]
}

# Constants
if _testnet:
    __wallet_rpc = RPCWrapper(CoinRPC(config["rpc-uri-test"], (config["rpc-user-test"], config["rpc-psw-test"])))
else:
    __wallet_rpc = RPCWrapper(CoinRPC(config["rpc-uri"], (config["rpc-user"], config["rpc-psw"])))
__rain_queue_filter = filters.Filters.group & (
        filters.Filters.text | filters.Filters.photo | filters.Filters.video | filters.Filters.reply | filters.Filters.forwarded
)
__rain_queue_min_text_length = config["rain"]["rain_queue_min_text_length"]
__rain_queue_min_words = config["rain"]["rain_queue_min_words"]
__rain_queue_max_members = config["rain"]["rain_queue_max_members"]
__rain_min_members = config["rain"]["rain_min_members"]
__rain_min_amount = config["rain"]["rain_min_amount"]

__unit = "IOC"

__rpc_getbalance_account = True  # If False use getbalance <address>
# If True, use getbalance <account> --If you still want to enable it, add to your config file enableaccounts=1
__rpc_sendmany_account = False  # If False, use sendmany <source_account> {"address": amount}, else {"account": amount}
__blockchain_explorer_tx = "https://chainz.cryptoid.info/ioc/tx.dws?"
__minconf = 0  # See issue #4 (https://github.com/DarthJahus/CashTip-Telegram/issues/4)

__standard_fee = 0.1
__withdrawal_fee = 1
__scavenge_fee = 1


# ToDo: Add service commands to check the health of the daemon / wallet.

def check_minimum(text):
    try:
        amount = float(str(text))
        if amount < 0.001:
            return 0.0
        return amount
    except:
        raise ValueError("Can't convert %s to float." % text)


def chat_type(update):
    if update.effective_chat is None:
        return "private"
    elif update.effective_chat.type == "private":
        return "private"
    else:
        return "group"


def can_use(update):
    if _paused:
        update.message.reply_text(text=emoji.emojize(strings.get("global_paused"), use_aliases=True), quote=True)
        return False
    #if not _spam_filter.verify(str(update.effective_user.id)):
    #    return False
    return True


def do_rpc_getbalance_account(update, _user_id, _address, method="undefined"):
    if __rpc_getbalance_account:
        _rpc_call = __wallet_rpc.getbalance(_user_id, __minconf)
    else:
        _rpc_call = __wallet_rpc.getreceivedbyaddress(_address, __minconf) # Show only the received, not a balance
    if not _rpc_call["success"]:
        log(method, _user_id, "getbalance > Error during RPC call: %s" % _rpc_call["message"])
        bad_rpc_connection(update)
    elif _rpc_call["result"]["error"] is not None:
        log(method, _user_id, "getbalance > Error: %s" % _rpc_call["result"]["error"])
    else:
        return check_minimum(_rpc_call["result"]["result"])
    return False


def do_rpc_getaddressesbyaccount(update, _user_id, method="undefined", force=False, ask=True):
    _rpc_call = __wallet_rpc.getaddressesbyaccount(_user_id)
    if not _rpc_call["success"]:
        log(method, _user_id, "getaddressesbyaccount > Error during RPC call: %s" % _rpc_call["message"])
        bad_rpc_connection(update)
    elif _rpc_call["result"]["error"] is not None:
        log(method, _user_id, "getaddressesbyaccount > Error: %s" % _rpc_call["result"]["error"])
    else:
        _addresses = _rpc_call["result"]["result"]
        if len(_addresses) == 0:
            # User has no address but need to receive a tip
            if force:
                _rpc_call = __wallet_rpc.getaccountaddress(_user_id)
                if not _rpc_call["success"]:
                    log(method, _user_id, "getaccountaddress > Error during RPC call: %s" %
                        _rpc_call["message"])
                elif _rpc_call["result"]["error"] is not None:
                    log(method, _user_id, "getaccountaddress > Error: %s" %
                        _rpc_call["result"]["error"])
                else:
                    return [_rpc_call["result"]["result"]]
            elif ask:
                # User has no address, ask him to create one
                msg_no_account(update)
            else:
                return []
            return False
        return _addresses
    return False


def do_rpc_sendmany(update, _user_id, _tip_dict, method="undefined"):
    _rpc_call = __wallet_rpc.sendmany(_user_id, _tip_dict)
    if not _rpc_call["success"]:
        log(method, _user_id, "sendmany > Error during RPC call: %s" % _rpc_call["message"])
        bad_rpc_connection(update)
    elif _rpc_call["result"]["error"] is not None:
        log(method, _user_id, "sendmany > Error: %s" % _rpc_call["result"]["error"])
    else:
        return _rpc_call["result"]["result"]
    return False


def do_rpc_sendfrom(update, _user_id, _recipient, _amount, method="undefined"):
    _rpc_call = __wallet_rpc.sendfrom(_user_id, _recipient, _amount)
    if not _rpc_call["success"]:
        log(method, _user_id, "sendfrom > Error during RPC call: %s" % _rpc_call["message"])
        bad_rpc_connection(update)
    elif _rpc_call["result"]["error"] is not None:
        log(method, _user_id, "sendfrom > Error: %s" % _rpc_call["result"]["error"])
    else:
        return _rpc_call["result"]["result"]
    return False


def bad_rpc_connection(update):
    update.message.reply_text(
        emoji.emojize(strings.get("error_making_rpc_call", _lang), use_aliases=True),
        quote=True,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )


def cmd_start(update, context):
    """Reacts when /start is sent to the bot."""
    if update.effective_chat.type == "private":
        if not _spam_filter.verify(str(update.effective_user.id)):
            return
        # Check for deep link
        if len(context.args) > 0:
            if context.args[0].lower() == "about":
                cmd_about()
            elif context.args[0].lower() == "help":
                cmd_help(update, context)
            elif context.args[0].lower() == "address":
                deposit(update)
            else:
                update.message.reply_text(
                    strings.get("error_bad_deep_link", _lang),
                    quote=True,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True
                )
        else:
            _button_help = InlineKeyboardButton(
                text=emoji.emojize(strings.get("button_help", _lang), use_aliases=True),
                callback_data="help"
            )
            _button_about = InlineKeyboardButton(
                text=emoji.emojize(strings.get("button_about", _lang), use_aliases=True),
                callback_data="about"
            )
            _markup = InlineKeyboardMarkup(
                [
                    [_button_help, _button_about]
                ]
            )
            update.message.reply_text(
                emoji.emojize(strings.get("welcome", _lang), use_aliases=True),
                quote=True,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
                reply_markup=_markup
            )


def cmd_about(update, context):
    if not _spam_filter.verify(str(update.effective_user.id)):
        return
    if update.effective_chat is None:
        _chat_type = "private"
    elif update.effective_chat.type == "private":
        _chat_type = "private"
    else:
        _chat_type = "group"
    #
    if _chat_type == "private":
        # Check if callback
        try:
            if update.callback_query.data is not None:
                update.callback_query.answer(strings.get("callback_simple", _lang))
        except:
            pass
        _button = InlineKeyboardButton(
            text=emoji.emojize(strings.get("button_help", _lang), use_aliases=True),
            callback_data="help"
        )
        _markup = InlineKeyboardMarkup(
            [[_button]]
        )
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=strings.get("about", _lang),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=_markup
        )
    else:
        _button = InlineKeyboardButton(
            text=emoji.emojize(strings.get("button_about", _lang), use_aliases=True),
            url="https://telegram.me/%s?start=about" % context.bot.username
        )
        _markup = InlineKeyboardMarkup(
            [[_button]]
        )
        update.message.reply_text(
            "%s" % strings.get("about_public", _lang),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=_markup
        )
    return True


def cmd_help(update, context):
    if not _spam_filter.verify(str(update.effective_user.id)):
        return
    if update.effective_chat is None:
        _chat_type = "private"
    elif update.effective_chat.type == "private":
        _chat_type = "private"
    else:
        _chat_type = "group"
    #
    if _chat_type == "private":
        # Check if callback
        try:
            if update.callback_query.data is not None:
                update.callback_query.answer(strings.get("callback_simple", _lang))
        except:
            pass
        _button = InlineKeyboardButton(
            text=emoji.emojize(strings.get("button_help_advanced_caption", _lang), use_aliases=True),
            url=strings.get("button_help_advanced_url", _lang)
        )
        _markup = InlineKeyboardMarkup(
            [[_button]]
        )
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=emoji.emojize(strings.get("help", _lang), use_aliases=True),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_markup,
            disable_web_page_preview=True
        )
    else:
        _button = InlineKeyboardButton(
            text=emoji.emojize(strings.get("button_help", _lang), use_aliases=True),
            url="https://telegram.me/%s?start=help" % context.bot.username
        )
        _markup = InlineKeyboardMarkup(
            [[_button]]
        )
        update.message.reply_text(
            "%s" % strings.get("help_public", _lang),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=_markup
        )
    return True


def msg_no_account(update):
    _button = InlineKeyboardButton(
        text=emoji.emojize(strings.get("user_no_address_button", _lang), use_aliases=True),
        url="https://telegram.me/%s?start=address" % config["telegram-botusername"]
    )
    _markup = InlineKeyboardMarkup(
        [[_button]]
    )
    update.message.reply_text(
        "%s" % strings.get("user_no_address", _lang),
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
        reply_markup=_markup,
    )


def deposit(update, context):
    """
    This commands works only in private.
    If the user has no address, a new account is created with his Telegram user ID (str)
    """
    if can_use(update) and chat_type(update) == "private":
        _username = update.effective_user.username
        if _username is None:
            _user_id = str(update.effective_user.id)
        else:
            _user_id = '@' + _username.lower()
        _addresses = do_rpc_getaddressesbyaccount(update, _user_id, "deposit", True)
        if _addresses:
            # ToDo: Can it happen that a user gets more than juan address? Verify.
            if _addresses[0] is not None:
                update.message.reply_text(
                    text="%s `%s`" % (strings.get("user_address", _lang), _addresses[0]),
                    quote=True,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True
                )


def balance(update, context):
    if can_use(update) and chat_type(update) == "private":
        _username = update.effective_user.username
        if _username is None:
            _user_id = str(update.effective_user.id)
        else:
            _user_id = '@' + _username.lower()
        _addresses = do_rpc_getaddressesbyaccount(update, _user_id, "balance")
        if _addresses:
            # ToDo: Handle the case when user has many addresses?
            # Maybe if something really weird happens and user ends up having more, we can calculate his balance.
            # This way, when asking for address (/deposit), we can return the first one.
            _address = _addresses[0]
            _balance = do_rpc_getbalance_account(update, _user_id, _address, "balance")
            if str(_balance) != str(False):
                update.message.reply_text(
                    text="%s\n`%f %s`" % (strings.get("user_balance", _lang), _balance, __unit),
                    parse_mode=ParseMode.MARKDOWN,
                    quote=True
                )


def tip(update, context):
    """
    /tip <user> <amount>
    /tip u1 u2 u3 ... v1 v2 v3 ...
    /tip u1 v1 u2 v2 u3 v3 ...
    """
    if not can_use(update) or len(context.args) < 2:
        return  # To avoid the long annoying error message that's shown when users misuse the command
    # Get recipients and values
    _message = update.effective_message.text
    _modifier = 0
    _handled = {}
    _recipients = []
    for entity in update.effective_message.entities:
        if entity.type == "text_mention":
            # UserId is unique
            _username = entity.user.name
            if str(entity.user.id) not in _handled:
                _handled[str(entity.user.id)] = (_username, entity.offset, entity.length)
                _recipients.append(str(entity.user.id))
        elif entity.type == "mention":
            # _username starts with @
            # _username is unique
            _username = update.message.parse_entity(entity).lower()
            #_username = update.effective_message.text[entity.offset:(entity.offset + entity.length)].lower()
            if _username not in _handled:
                _handled[_username] = (_username, entity.offset, entity.length)
                _recipients.append(_username)
        _part = _message[:entity.offset - _modifier]
        _message = _message[:entity.offset - _modifier] + _message[entity.offset + entity.length - _modifier:]
        _modifier = entity.offset + entity.length - len(_part)
    _amounts = _message.split()
    # check if amounts are all convertible to float
    _amounts_float = []
    try:
        for _amount in _amounts:
            _amounts_float.append(check_minimum(_amount))
    except:
        _amounts_float = []
    # Make sure number of recipients is the same as number of values
    # old: if len(_amounts_float) != len(_recipients) or len(_amounts_float) == 0 or len(_recipients) == 0:
    # new: ((len(_amounts_float) == len(_recipients)) or (len(_amounts_float) == 1)) and (len(_recipients) > 0),
    # use opposite
    if ((len(_amounts_float) != len(_recipients)) and (len(_amounts_float) != 1)) or (len(_recipients) == 0):
        update.message.reply_text(
            text=strings.get("tip_error_arguments", _lang),
            quote=True,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        do_tip(update, context, _amounts_float, _recipients, _handled)


def do_tip(update, context, amounts_float, recipients, handled, verb="tip"):
    """
    Send amounts to recipients
    :param context:
    :param update: Update
    :param amounts_float: Array of Float
    :param recipients: Array of Username or UserID
    :param handled: Dict of {"username or UserID": (username, entity.offset, entity.length)
    :param verb: "tip", will be used in "%verb%_success" and "%verb%_missing_recipient" strings
    :return: None
    """
    #
    if verb not in ["tip", "rain"]:
        log("do_tip", "__system__", "Incorrect verb passed to do_tip()")
        verb = "tip"
    # Check if only 1 amount is given
    _amounts_float = amounts_float
    if len(_amounts_float) == 1 and len(recipients) > 1:
        _amounts_float = _amounts_float * len(recipients)
    # Check if user has enough balance
    _username = update.effective_user.username
    if _username is None:
        _user_id = str(update.effective_user.id)
    else:
        _user_id = '@' + _username.lower()
    _addresses = do_rpc_getaddressesbyaccount(update, _user_id, "do_tip")
    if _addresses:
        _address = _addresses[0]
        _balance = do_rpc_getbalance_account(update, _user_id, _address, "do_tip")
        if _balance:
            _balance = int(_balance)
            # Now, finally, check if user has enough funds (includes tx fee)
            _fee = max(__standard_fee, int(len(recipients) / 3) * __standard_fee)
            if sum(_amounts_float) > _balance - _fee:
                update.message.reply_text(
                    text="%s `%i %s`" % (strings.get("tip_no_funds", _lang), sum(_amounts_float) + _fee, __unit),
                    quote=True,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                # Now create the {recipient_id: amount} dictionary
                i = 0
                _tip_dict_addresses = {}
                _tip_dict_accounts = {}
                for _recipient in recipients:
                    # add "or _recipient == bot.id" to disallow tipping the tip bot
                    if _recipient == _user_id:
                        i += 1
                        continue
                    if _recipient[0] == '@':
                        # ToDo: Get the id (actually not possible (Bot API 3.6, Feb. 2018)
                        # See issue #2 (https://github.com/DarthJahus/PandaTip-Telegram/issues/2)
                        # Using the @username
                        # Done: When requesting a new address, if user has a @username, then use that username (2018-07-16)
                        # Problem: If someone has no username, then later creates one, he loses access to his account
                        # Done: Create a /scavenge command that allows people who had UserID to migrate to UserName (2018-07-16)
                        _recipient_id = _recipient.lower()  # Enforce lowercase
                    else:
                        _recipient_id = _recipient
                    # Check if recipient has an address (required for .sendmany())
                    _addresses = do_rpc_getaddressesbyaccount(update, _recipient_id, "do_tip:%s" % _recipient, True)
                    if _addresses[0] is not None:
                        # Because recipient has an address, we can add him to the dict
                        _tip_dict_accounts[_recipient_id] = _amounts_float[i]
                        _tip_dict_addresses[_addresses[0]] = _amounts_float[i]
                    i += 1
                #
                _tip_dict = {}
                if __rpc_sendmany_account:
                    _tip_dict = _tip_dict_accounts
                else:
                    _tip_dict = _tip_dict_addresses
                # Check if there are users left to tip
                if len(_tip_dict) == 0:
                    update.message.reply_text(
                        text="%s" % (strings.get("tip_no_receiver", _lang)),
                        quote=True,
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    _tx = do_rpc_sendmany(update, _user_id, _tip_dict, "do_tip")
                    if _tx:
                        _suppl = ""
                        if len(_tip_dict) != len(recipients):
                            _suppl = "\n\n_%s_" % strings.get("%s_missing_recipient" % verb, _lang)
                        update.message.reply_text(
                            text="*%s* %s\n%s\n\n[tx %s](%s)%s" % (
                                update.effective_user.name,
                                strings.get("%s_success" % verb, _lang),
                                ''.join((("\n- `%.3f %s ` %s *%s*" % (
                                    _tip_dict_accounts[_recipient_id], __unit,
                                    strings.get("%s_preposition" % verb, _lang),
                                    handled[_recipient_id][0])) for _recipient_id in _tip_dict_accounts)),
                                _tx[:4] + "..." + _tx[-4:],
                                __blockchain_explorer_tx + _tx,
                                _suppl
                            ),
                            quote=True,
                            parse_mode=ParseMode.MARKDOWN,
                            disable_web_page_preview=True
                        )


def damp_rock(update, context):
    """
    Manages a queue of active users.
    Activity type is checked before calling this function.
    Message length should be enforced to avoid spam.
    :param bot: Bot
    :param update: Update
    :return: None
    """
    if _paused:
        return
    if update.effective_chat is None:
        return
    elif update.effective_chat.type not in ["group", "supergroup"]:
        return
    _group_id = str(update.effective_chat.id)
    if update.effective_user.is_bot:
        return
    # Get user_id for the tip command (either @username or else UserID)
    _username = update.effective_user.username
    _user_id = str(
        update.effective_user.id)  # The queue uses real UserID to avoid registering a user twice if user creates @
    if _username is None:
        _user_id_local = _user_id
        _user_readable_name = update.effective_user.name
    else:
        _user_id_local = '@' + _username.lower()
        _user_readable_name = _username
    if update.effective_message.text is not None:
        if len(update.effective_message.text) < __rain_queue_min_text_length:
            return
        if len(update.effective_message.text.split()) < __rain_queue_min_words:
            return
    # Check the queue
    if _group_id not in _rain_queues:
        _rain_queues[_group_id] = []
    # Note: In Python2, Dict doesn't preserve order as in Python3 (see https://stackoverflow.com/questions/14956313)
    if len(_rain_queues[_group_id]) > 0:
        # If user has talked last, don't remove it, don't add it.
        if _rain_queues[_group_id][0][0] == _user_id:  # Don't use "is not", the object will not be the same,
            # only value will
            return
        else:
            # Search for user and remove it (in order to place it first)
            for _user_data in _rain_queues[_group_id]:
                if _user_data[0] == _user_id:
                    _rain_queues[_group_id].remove(_user_data)
                    break
    # Add user to queue (first, since it will be read from first to last)
    _rain_queues[_group_id].insert(0, (_user_id, _user_id_local, _user_readable_name))
    # Check if the queue has to be pruned
    if len(_rain_queues[_group_id]) > __rain_queue_max_members:
        _rain_queues[_group_id].pop()  # pop(-1). This should be enough to remove the last member,
        # but real pruning would be better


def rain(update, context):
    if not can_use(update):
        return
    if update.effective_chat is None:
        return
    elif update.effective_chat.type not in ["group", "supergroup"]:
        return
    #
    _group_id = str(update.effective_chat.id)
    _user_id = str(update.effective_user.id)
    if 0 < len(context.args) <= 2:  # We may or may not allow text after the first 2 arguments. Probably not.
        # Check if queue has enough members
        if _group_id not in _rain_queues:
            update.message.reply_text(
                strings.get("rain_queue_not_initialized", _lang),
                quote=True,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            return
        # Prepare arguments
        _rain_amount_demanded = 0
        _rain_members_demanded = __rain_queue_max_members  # number of members = min(optional args[1], queue_max, queue_len)
        try:
            _rain_amount_demanded = int(context.args[0])
            if len(context.args) > 1:
                _rain_members_demanded = int(context.args[1])
        except ValueError:
            return  # Don't show error. Probably trolling.
        if _rain_amount_demanded < __rain_min_amount:
            update.message.reply_text(
                strings.get("rain_queue_min_amount", _lang) % (
                    __rain_min_amount, __unit, _rain_amount_demanded, __unit),
                quote=True,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            return
        if _rain_members_demanded < __rain_min_members or _rain_members_demanded > __rain_queue_max_members:
            update.message.reply_text(
                strings.get("rain_queue_min_max_members", _lang) % (
                    __rain_min_members, __rain_queue_max_members, _rain_members_demanded),
                quote=True,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            return
        # Check if user is in queue, don't remove user from original queue as recipients array will be created later
        # Note that using this command doesn't put the user in queue (commands are excluded from damp_rock())
        _modifier = 0
        for _user_data in _rain_queues[_group_id]:
            if _user_data[0] == _user_id:
                _modifier = -1
                break
        # Check if there are enough members in queue (minus user if needed)
        if len(_rain_queues[_group_id]) + _modifier < __rain_min_members:
            update.message.reply_text(
                strings.get("rain_queue_not_enough_members", _lang) % (
                    len(_rain_queues[_group_id]) + _modifier,
                    - _modifier,
                    __rain_min_members
                ),
                quote=True,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            return
        # Prepare queue for tips
        _recipients = []  # Array of LocalUserID
        _handled = {}  # Dict of LocalUserID: (Readable Name, Unused, Unused)
        for _user_data in _rain_queues[_group_id]:
            if _user_data[0] != _user_id:
                _recipients.append(_user_data[1])  # Local UserID (@username or else UserID)
                _handled[_user_data[1]] = (_user_data[2], None, None)
                if len(_recipients) >= _rain_members_demanded:
                    break
        log("rain", _user_id,
            "rain (%i over %i members) handed to do_tip()" % (_rain_amount_demanded, len(_recipients)))
        do_tip([_rain_amount_demanded], _recipients, _handled, verb="rain")


def withdraw(update, context):
    """
    Withdraw to an address. Works only in private.
    """
    if _paused:
        update.message.reply_text(text=emoji.emojize(strings.get("global_paused"), use_aliases=True), quote=True)
        return
    if chat_type(update) == "private":
        if not _spam_filter.verify(str(update.effective_user.id)):
            return
        _amount = None
        _recipient = None
        if len(context.args) == 2:
            try:
                _amount = check_minimum(context.args[1])
                _recipient = context.args[0]
            except:
                try:
                    _amount = check_minimum(context.args[0])
                    _recipient = context.args[1]
                except:
                    pass
        else:
            update.message.reply_text(
                text="Too few or too many arguments for this command.",
                quote=True
            )
        if _amount is not None and _recipient is not None:
            _username = update.effective_user.username
            if _username is None:
                _user_id = str(update.effective_user.id)
            else:
                _user_id = '@' + _username.lower()
            # get address of user
            _addresses = do_rpc_getaddressesbyaccount(update, _user_id, "withdraw")
            if _addresses:
                _address = _addresses[0]
                _balance = do_rpc_getbalance_account(update, _user_id, _address, "withdraw")
                if _balance:
                    _balance = int(_balance)
                    if _balance < _amount + __withdrawal_fee:
                        update.message.reply_text(
                            text="%s `%i %s`" % (
                                strings.get("withdraw_no_funds", _lang), max(0, _balance - __withdrawal_fee),
                                __unit),
                            quote=True,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    else:
                        # Withdraw
                        _tx = do_rpc_sendfrom(update, _user_id, _recipient, _amount, method="withdraw")
                        if _tx:
                            update.message.reply_text(
                                text="%s\n[tx %s](%s)" % (
                                    strings.get("withdraw_success", _lang),
                                    _tx[:4] + "..." + _tx[-4:],
                                    __blockchain_explorer_tx + _tx
                                ),
                                quote=True,
                                parse_mode=ParseMode.MARKDOWN,
                                disable_web_page_preview=True
                            )


def scavenge(update, context):
    if _paused:
        update.message.reply_text(text=emoji.emojize(strings.get("global_paused"), use_aliases=True), quote=True)
        return
    if chat_type(update) == "private":
        if not _spam_filter.verify(str(update.effective_user.id)):
            return
        _username = update.effective_user.username
        if _username is None:
            update.message.reply_text(
                text="Sorry, this command is not for you.",
                quote=True
            )
        else:
            _username = '@' + _username.lower()
            _user_id = str(update.effective_user.id)
            _addresses = do_rpc_getaddressesbyaccount(update, _user_id, "scavenge", False, False)
            if _addresses:
                if len(_addresses) == 0:
                    update.message.reply_text(
                        text="%s (`%s`)" % (strings.get("scavenge_no_address", _lang), _user_id),
                        quote=True,
                    )
                else:
                    _address = _addresses[0]
                    _balance = do_rpc_getbalance_account(update, _user_id, _address, "scavenge")
                    if _balance:
                        _balance = int(_balance)
                        # Done: Move balance from UserID to @username if balance > 5 (2018-07-16)
                        if _balance <= 5:
                            update.message.reply_text(
                                text="%s (`ID %s`)." % (strings.get("scavenge_empty", _lang), _user_id),
                                parse_mode=ParseMode.MARKDOWN,
                                quote=True
                            )
                        else:
                            # Need to make sure there is an account for _username
                            _addresses = do_rpc_getaddressesbyaccount(update, _username, "scavenge2", True)
                            if _addresses:
                                _address = _addresses[0]
                                if _address is not None:
                                    # Move the funds from UserID to Username
                                    _tx = do_rpc_sendfrom(update, _user_id, _address,
                                                          _balance - __scavenge_fee, method="scavenge")
                                    if _tx:
                                        update.message.reply_text(
                                            text="%s (`%s`).\n%s `%i %s`\n[tx %s](%s)" % (
                                                strings.get("scavenge_success_1", _lang),
                                                _user_id,
                                                strings.get("scavenge_success_2", _lang),
                                                _balance - __scavenge_fee,
                                                __unit,
                                                _tx[:4] + "..." + _tx[-4:],
                                                __blockchain_explorer_tx + _tx,
                                            ),
                                            quote=True,
                                            parse_mode=ParseMode.MARKDOWN,
                                            disable_web_page_preview=True
                                        )


def cmd_get_log(update, context):
    """
    Send logs to (admin) user
    """
    # Note: Don't use emoji in caption
    if update.effective_chat.id in config["admins"]:
        with open("log.csv", "rb") as _file:
            _file_name = "%s-log-%s.csv" % (
                context.bot.username, datetime.fromtimestamp(time.time()).strftime("%Y-%m-%dT%H-%M-%S"))
            context.bot.sendDocument(
                chat_id=update.effective_user.id,
                document=_file,
                reply_to_message_id=update.message.message_id,
                caption="Here you are!",
                filename=_file_name
            )
        log(fun="cmd_send_log", user=str(update.effective_user.id),
            message="Log sent to admin '%s'." % update.effective_user.name)


def cmd_clear_log(update, context):
    if update.effective_chat.id in config["admins"]:
        clear_log()
        update.message.reply_text(text=emoji.emojize(strings.get("clear_log_done"), use_aliases=True))


def cmd_pause(update, context):
    # Admins only
    if update.effective_chat.id in config["admins"]:
        global _paused
        _paused = not _paused
        _answer = ""
        if _paused:
            _answer = strings.get("pause_answer_paused")
        else:
            _answer = strings.get("pause_answer_resumed")
        update.message.reply_text(emoji.emojize(_answer, use_aliases=True), quote=True)
        # Reinitialize rain queues
        _rain_queues.clear()


def cmd_queue(update, context):
    # Admins only
    if update.effective_user.id in config["admins"]:
        _chat_id = str(update.effective_chat.id)
        if _chat_id in _rain_queues:
            update.message.reply_text("There are %i users in queue." % len(_rain_queues[_chat_id]), quote=True)
        else:
            update.message.reply_text("Chat not found in queues", quote=True)


if __name__ == "__main__":
    updater = Updater(token=config["telegram-token"], use_context=True)
    dispatcher = updater.dispatcher
    # TGBot commands
    dispatcher.add_handler(CommandHandler("start", cmd_start, pass_args=True))
    dispatcher.add_handler(CommandHandler("help", cmd_help))
    dispatcher.add_handler(CallbackQueryHandler(callback=cmd_help, pattern=r'^help$'))
    dispatcher.add_handler(CommandHandler("about", cmd_about))
    dispatcher.add_handler(CallbackQueryHandler(callback=cmd_about, pattern=r'^about$'))
    # Tipbot commands
    dispatcher.add_handler(CommandHandler("tip", tip, pass_args=True))
    dispatcher.add_handler(CommandHandler("withdraw", withdraw, pass_args=True))
    dispatcher.add_handler(CommandHandler("deposit", deposit))
    dispatcher.add_handler(CommandHandler("address", deposit))  # alias for /deposit
    dispatcher.add_handler(CommandHandler("balance", balance))
    dispatcher.add_handler(CommandHandler("scavenge", scavenge))
    dispatcher.add_handler(CommandHandler("rain", rain, pass_args=True))
    # Admin commands
    dispatcher.add_handler(CommandHandler("get_log", cmd_get_log))
    dispatcher.add_handler(CommandHandler("clear_log", cmd_clear_log))
    dispatcher.add_handler(CommandHandler("pause", cmd_pause))  # pause / unpause
    dispatcher.add_handler(CommandHandler("queue", cmd_queue))  # get length of the queue
    # This will be needed for rain
    dispatcher.add_handler(MessageHandler(__rain_queue_filter, damp_rock))
    #
    updater.start_polling()
    log("__main__", "__system__", "Started service!")
