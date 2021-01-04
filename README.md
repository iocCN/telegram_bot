# Telegram Bot
> Based on [PandaTip-Telegram](https://github.com/DarthJahus/PandaTip-Telegram), by @DarthJahus

This bot pretend to promote the use of iocoin on the telegrams users.

## Docker

The Dockerfile is provided, so you can build your own Docker image and use it. In order to run the tips commands, you need provide an RPC source, so a iocoin node is needed.

## Usage

### Configuration file

Create a `config.json` **JSON** file and set up the following parameters:

(sample)
 
    {
    	"telegram-token": "such:sicret-token",
    	"telegram-botname": "IOC test Bot",
    	"telegram-botusername": "iocBot",
    	"rpc-uri": "http://127.0.0.1:33765",
    	"rpc-user": "your-user",
    	"rpc-psw": "your-password",
    	"rpc-uri-test": "http://127.0.0.1:43765",
    	"rpc-user-test": "your-testnet-user",
    	"rpc-psw-test": "your-testnet-password",
    	"admins": [-0, 0],
    	"spam_filter": [5, 60],
    	"rain": {
    	    "rain_queue_min_text_length": 10,
    	    "rain_queue_min_words": 2,
    	    "rain_queue_max_members": 30,
    	    "rain_min_members": 5,
    	    "rain_min_amount": 10
    	}
    }

* `telegram-token`: Your bot's unique and secret token.
  > Create a new bot by talking with [@BotFather](https://t.me/BotFather) to get one. 
* `rpc-uri`: Address and port for the daemon.
  > We do not advice to expose the port to external network. Please, be cautious.
  > See [next section](#IOCoin-daemon-configuration) to allow access for network addresses.
* `rpc-user`, `rpc-psw`: Username and password for the daemon.
  > You can set them in the `iocoin.conf` file ([see next section](#IOCoin-daemon-configuration)).
* `admins`: An array of administrators' Telegram UserID (as integers).
  > You can send `/user_id` to [@ContremaitreBot](https://t.me/ContremaitreBot) to know your UserID.
* `spam_filter`: An array of two integers. The first value is the number of actions a user can perform in a period of time, the 2nd value defines that period of time in seconds.
  > `"spam_filter": [5, 60]` means that users cannot perform more than 5 actions per minute.


### IOCoin daemon configuration

To achieve a properly integration, the `iocoin.conf` file need some arguments, e.g.:

    server=1
    daemon=1
    enableaccounts=1
    staking=0
    rpcuser=your-user
    rpcpassword=your-password
    rpcallowip=127.0.0.1
    rpcconnect=127.0.0.1

### Donations

With each donation received, we become all that much closer to our goal.

IOC address `iTVMSGJoPqwkpY4bH7ukxvknWrnCwWQkc4`

BTC address `1BJpETZDrHWvruQQhzCtNDqAX6W5WutGG9`

Thank you for making a difference through your compassion and generosity.

---
