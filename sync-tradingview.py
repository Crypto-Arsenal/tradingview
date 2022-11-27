class Strategy(StrategyBase):
    def __init__(self):
        self.period = 60
        self.subscribed_books = {}
        self.options = {}
        exchange, pair, base, quote = CA.get_exchange_pair()
        quote_balance = CA.get_balance(exchange, quote)
        # self.initial_capital = quote_balance.available
        self.ca_initial_capital = quote_balance.available
        CA.log('Total inital ' + str(quote) + ' quote amount: ' + str(self.initial_capital))

    def on_tradingview_signal(self, signal, candles):
        exchange, pair, base, quote = CA.get_exchange_pair()
        log = signal.get('log')
        CA.log('📩 TradingView log: ' + str(log))

        """
        comment:{{strategy.order.comment}}/base_amount/{{strategy.market_position}}/{{strategy.market_position_size}}/{{strategy.prev_market_position}}/{{strategy.prev_market_position_size}}
        {{strategy.order.alert_message}}/{{strategy.market_position}}/{{strategy.market_position_size}}/{{strategy.prev_market_position}}/{{strategy.prev_market_position_size}}
        {
            "log": {{strategy.order.comment}}, 
            "position": {
                "capital": 100,
                "order_size": {{strategy.order.contracts}},
                "order_price": {{strategy.order.price}},
                "position": "{{strategy.market_position}}", 
                "position_size": "{{strategy.market_position_size}}",
                "prev_position": "{{strategy.prev_market_position}}",
                "prev_position_size": "{{strategy.prev_market_position_size}}"
            },
            "connectorName":"alan wu-TV-11759",
            "connectorToken":"648f4149-5721-47cc-8a48-cee09a32dd8f"
        }
        """

        position = signal.get('position')
        if not position:
            return CA.log('⛔ Invalid signal')

        tv_capital = position.get("capital")
        tv_position = self.get_position_from_size_and_side(position.get("position_size"), position.get("position"))
        tv_prev_position = self.get_position_from_size_and_side(position.get("prev_position_size"), position.get("prev_position"))
        tv_order_size = position.get("order_size")
        tv_order_price = position.get("order_price")

        # 檢查訊號正確性
        if tv_capital is None or tv_position is None or tv_prev_position is None or tv_order_size is None or tv_order_price is None:
            return CA.log('⛔ Invalid signal')

        ca_position, _ = self.get_ca_position()
        quote_balance = CA.get_balance(exchange, quote)
        ca_available_capital = quote_balance.available


        """
         - 如果 new > prev 那ＴＶ在加倉或是開倉 
         - 用 tv_capital 算出 要開 compound_capital 的幾 % 
        """
        if abs(tv_position - tv_prev_position) > abs(tv_prev_position):
            # 用下單金額和權益去反推TV下單%
            tv_order_percent_of_capitial = (tv_order_size * tv_order_price) / tv_capital

            # # 看我們現在的倉位是用多少%的本金下去開的 如果2顆是用10%開的->1顆是5%->那現在倉位是3代表我們TV用了15%去開倉了
            # tv_position_percent_of_capital = (tv_position / tv_order_size) * tv_order_percent_of_capitial
            
            # # 看CA的倉位已經用了多少%的本金去開了
            # ca_position_percent_of_capital = (self.ca_initial_capital - ca_available_capital) / self.ca_initial_capital

            # 看CA的倉位%跟TV還差多少 （我們要開多少%的倉位)
            # percent_of_cap = tv_position_percent_of_capital - ca_position_percent_of_capital

            CA.log("開單比例 % " + str(tv_order_percent_of_capitial * 100))

            # 用CA空倉時的金額去下開或加倉的金額 不行超過 1
            notion = self.ca_initial_capital * min(tv_order_percent_of_capitial, 1)
            
            # close short -> open long 不用管 prev_tv_position 因為我們知道一定會開多 但是要先確保 CA 倉位是對的
            if tv_position > 0 and ca_position < 0:
                return CA.place_order(exchange, pair, action='close_short', conditional_order_type='OTO', percent=100,
                                   child_conditional_orders=[{'action': 'open_long',  'notion': notion}])

            # close long -> open short 不用管 prev_tv_position 因為我們知道一定會開空 但是要先確保 CA 倉位是對的
            elif tv_position < 0 and ca_position > 0:
                return CA.place_order(exchange, pair, action='close_long', conditional_order_type='OTO', percent=100,
                                   child_conditional_orders=[{'action': 'open_short',  'notion': notion}])

            # CA 倉位是在對的方向
            action = "open_long" if tv_position > 0 else "open_short"
            return CA.place_order(exchange, pair, action=action, notion=notion)
    
        elif abs(tv_position - tv_prev_position) < abs(tv_prev_position):
            # 用TV前和後倉位去看關了多少 不行超過 1
            tv_order_percent_of_position = min((tv_prev_position - tv_position) / tv_prev_position, 1) * 100
            
            CA.log("關倉比例 % " + str(tv_order_percent_of_position))

            action = "close_long" if tv_prev_position > 0 else "close_short"
            return CA.place_order(exchange, pair, action=action, percent=tv_order_percent_of_position)
        else:
            CA.log("⛔ No action")

    def trade(self, candles):
        pass
    
    def on_order_state_change(self,  order):
        if order.status == CA.OrderStatus.FILLED:
            CA.log('🎉 LATEST POS: ' + str(self.get_ca_position()[0]))

        # 平倉時 設置新的開倉金
        if self.get_ca_position() == 0:
            exchange, pair, base, quote = CA.get_exchange_pair()
            quote_balance = CA.get_balance(exchange, quote)
            self.ca_initial_capital = quote_balance.available
            

    def get_position_from_size_and_side(self, positionSize, positionSide):
        if positionSide is None or positionSize is None:
            return None
        if positionSide ==  "long":
            return abs(positionSize)
        elif positionSide == "short":
            return abs(positionSize) * -1
        elif positionSide == "flat":
            return 0 # not sure
        return None

        # return current total position: -n 0, +n  where n is number of contracts
    def get_ca_position(self):
        exchange, pair, base, quote = CA.get_exchange_pair()

        long_position = CA.get_position(exchange, pair, CA.PositionSide.LONG)
        if long_position:
            return abs(long_position.total_size)

        short_position = CA.get_position(exchange, pair, CA.PositionSide.SHORT)
        if short_position:
            return -1 * abs(short_position.total_size)

        return  0
