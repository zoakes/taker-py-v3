from .helpers.exceptions import InvalidUsage
import os
from .helpers.validation import *
from .helpers.common import RfqType
import aiohttp


class HashflowApi:
    def __init__(self, mode, name, auth_key, environment="production"):
        self.headers = {"Authorization": auth_key}
        if environment == "production":
            self.host = "https://api.hashflow.com"
        elif environment == "staging":
            self.host = "https://api-staging.hashflow.com"
        else:
            raise InvalidUsage(f"Invalid value {environment} for environment")

        if mode == "wallet":
            self.source = "api"
            self.wallet = name
        elif mode == "taker":
            self.source = name
            self.wallet = None
        else:
            raise InvalidUsage(f"Invalid value {mode} for mode")
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.session.close()

    async def get_market_makers(self, chain_id, wallet=None, market_maker=None):
        validate_chain_id(chain_id)
        params = {
            "source": self.source,
            "baseChainType": 'evm',
            "baseChainId": str(chain_id),
        }
        if wallet is not None:
            params["wallet"] = wallet
        if market_maker is not None:
            params["marketMaker"] = market_maker

        async with self.session.get(f"{self.host}/taker/v3/market-makers", headers=self.headers, params=params) as r:
            r.raise_for_status()
            json = await r.json()
            return json["marketMakers"]

    async def get_price_levels(self, chain_id, market_makers):
        """

        GET https://api.hashflow.com/taker/v3/price-levels
          ?source=<source>
          &baseChainType=<string>
          &baseChainId=<string>
          &marketMakers[]=<mm1>
          &marketMakers[]=<mm2>
          &baseToken=<token address> //optional
          &quotToken=<token address> //optional

        :param chain_id:
        :param market_makers:
        :return:
        """
        validate_chain_id(chain_id)
        params = {
            "source": self.source,
            'baseChainId': str(chain_id),
            'baseChainType': 'evm',
            "marketMakers[]": market_makers,
            # baseToken:   # optional
            # quoteToken:  # optional

        }
        if self.wallet is not None:
            params["wallet"] = self.wallet

        async with self.session.get(f"{self.host}/taker/v3/price-levels", headers=self.headers, params=params) as r:
            r.raise_for_status()
            json = await r.json()
            return json["levels"]



    async def request_quote(
            self,
            chain_id,
            base_token,
            quote_token,
            dst_chain_id=None,
            base_token_amount=None,
            quote_token_amount=None,
            wallet=None,
            effective_trader=None,
            market_makers=None,
            feeBps=None,
            debug=False,
    ):
        """
        Post the RFQ according to the new API documentation.

        POST https://api.hashflow.com/taker/v3/rfq

        // JSON body
        {
          source: string, // Your identifier (e.g. "1inch", "zerion")
          baseChain: {
            chainType: string, // evm | solana
            chainId: number
          }
          quoteChain: {
            chainType: string, // evm | solana
            chainId: number
          }
          rfqs: {
            // Contract address (e.g. "0x123a...789")
            baseToken: string,
            // Contract address (e.g. "0x123a...789")
            quoteToken: string,
            // Decimal amount (e.g. "1000000" for 1 USDT)
            baseTokenAmount: ?string
            // Decimal amount (e.g. "1000000" for 1 USDT)
            quoteTokenAmount: ?string,
            // The address that will receive quoteToken on-chain.
            trader: string,
            // The wallet address of the actual trader (e.g. end user wallet).
            // If effectiveTrader is not present, we assume trader == effectiveTrader.
            effectiveTrader: ?string,
            // The wallet address to claim trading rewards for api user.
            // Cannot be set unless source == 'api'
            // This is useful when api users needs a separate wallet to claim rewards
            // If left empty, rewards will be sent to trader address
            rewardTrader: ?string,

            marketMakers: ?string[], // e.g. ["mm1"]
            excludeMarketMakers: ?string[],
            options:{
              doNotRetryWithOtherMakers: ?boolean, //Default to false
            }

            // The amount to be charged in fees, in basis points.
            feesBps: ?number
          }[],
          calldata: ?boolean, // If this is true, contract calldata will be provided.
        }
        """
        # ... your existing validation logic ...

        trader = wallet if wallet is not None else self.wallet
        if trader is None:
            raise InvalidUsage("Must specify wallet for trader.")

        # Construct the new request body structure
        rfqs = [{
            "baseToken": base_token,
            "quoteToken": quote_token,
            "baseTokenAmount": base_token_amount,
            "quoteTokenAmount": quote_token_amount,
            "trader": trader,
            "effectiveTrader": effective_trader or trader,  # Assume trader == effectiveTrader if not specified
            "marketMakers": market_makers,
            "feesBps": feeBps,
        }]

        data = {
            "source": self.source,
            "baseChain": {
                "chainType": "evm",  # Assuming EVM chain type
                "chainId": chain_id,
            },
            "quoteChain": {
                "chainType": "evm",  # Assuming EVM chain type
                "chainId": dst_chain_id or chain_id,
            },
            "rfqs": rfqs,
            "calldata": debug,
            # this is basically, debugging
        }

        # Assuming the endpoint is now v3 instead of v2
        async with self.session.post(f"{self.host}/taker/v3/rfq", json=data, headers=self.headers) as r:
            r.raise_for_status()
            return await r.json()


if __name__ == "__main__":
    import asyncio

    async def main():
        async with HashflowApi(
            mode="taker",
            name="qa",
            auth_key=os.environ["HASHFLOW_AUTHORIZATION_KEY"],
            environment="production",
        ) as api:
            makers = await api.get_market_makers(1, market_maker="mm5")
            print(makers)
            levels = await api.get_price_levels(1, ["mm4", "mm5"])
            print(levels)
            wallet = os.environ["HASHFLOW_TEST_WALLET"]
            quote = await api.request_quote(
                chain_id=1,
                base_token="0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
                quote_token="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                quote_token_amount="18364991",
                wallet=wallet,
                market_makers=["mm5", "mm4"],
                feeBps=2,
                debug=True,
            )
            print(quote)
    asyncio.run(main())