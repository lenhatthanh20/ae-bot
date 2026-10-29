//+------------------------------------------------------------------+
//| AIGold.mq5 - the AI proposes, this EA decides.                   |
//+------------------------------------------------------------------+
#property version "1.00"
#include <Trade/Trade.mqh>

input string          InpSymbol          = "XAUUSD";   // exact broker symbol
input ENUM_TIMEFRAMES InpTimeframe       = PERIOD_M15;
input string          InpUrl             = "http://127.0.0.1:18765/decide";
input int             InpTimeoutMs       = 60000;
input bool            InpDryRun          = true;
input bool            InpAllowLive       = false;
input long            InpMagic           = 20261029;
input double          InpLots            = 0.01;
input int             InpStartHourGMT    = 7;
input int             InpEndHourGMT      = 17;
input int             InpFridayCloseGMT  = 19;
input int             InpMaxHoldBars     = 16;
input int             InpMaxSpreadPts    = 40;
input int             InpMinConfidence   = 70;
input int             InpMaxTradesPerDay = 3;
input double          InpMaxDailyLossPct = 2.0;
input double          InpMaxDrawdownPct  = 10.0;
input double          InpMaxRiskPct      = 1.0;
input double          InpSlMinAtr        = 1.0;
input double          InpSlMaxAtr        = 2.5;
input double          InpMinRR           = 1.5;
input double          InpMaxRR           = 3.0;
input double          InpMaxTpAtr        = 4.0;
input double          InpMinSlSpreads    = 6.0;
input double          InpMaxDriftAtr     = 0.3;
input int             InpSlippagePts     = 30;
input bool            InpNewsFilter      = true;
input int             InpNewsMinutes     = 30;
input int             InpBars            = 100;
input int             InpHtfBars         = 30;         // closed H1 and H4 bars sent for context

CTrade trade;
string g_sym;
int    hE20 = INVALID_HANDLE, hE50 = INVALID_HANDLE, hE200 = INVALID_HANDLE;
int    hRsi = INVALID_HANDLE, hAtr = INVALID_HANDLE;
string g_gvBar, g_gvDay, g_gvEq, g_gvPeak;

int OnInit()
{
   if(AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL && !InpAllowLive)
   {
      Print("REAL account and InpAllowLive=false: refusing to start");
      return INIT_FAILED;
   }
   g_sym = InpSymbol;
   if(!SymbolSelect(g_sym, true))
   {
      PrintFormat("symbol %s not found: set InpSymbol to the broker name", g_sym);
      return INIT_FAILED;
   }
   if(_Symbol != g_sym)
      PrintFormat("WARNING: attach to a %s chart; OnTick follows the chart symbol", g_sym);

   hE20  = iMA(g_sym, InpTimeframe, 20, 0, MODE_EMA, PRICE_CLOSE);
   hE50  = iMA(g_sym, InpTimeframe, 50, 0, MODE_EMA, PRICE_CLOSE);
   hE200 = iMA(g_sym, InpTimeframe, 200, 0, MODE_EMA, PRICE_CLOSE);
   hRsi  = iRSI(g_sym, InpTimeframe, 14, PRICE_CLOSE);
   hAtr  = iATR(g_sym, InpTimeframe, 14);
   if(hE20 == INVALID_HANDLE || hE50 == INVALID_HANDLE || hE200 == INVALID_HANDLE ||
      hRsi == INVALID_HANDLE || hAtr == INVALID_HANDLE)
      return INIT_FAILED;

   trade.SetExpertMagicNumber((ulong)InpMagic);
   trade.SetDeviationInPoints((ulong)InpSlippagePts);
   trade.SetTypeFillingBySymbol(g_sym);

   string p = "AIGold_" + IntegerToString(InpMagic) + "_";
   g_gvBar = p + "lastbar"; g_gvDay = p + "day"; g_gvEq = p + "dayeq"; g_gvPeak = p + "peak";

   PrintFormat("%s digits=%d point=%g tick=%g contract=%g stops=%d freeze=%d spread_now=%d pts dryrun=%s",
               g_sym, (int)SymbolInfoInteger(g_sym, SYMBOL_DIGITS), SymbolInfoDouble(g_sym, SYMBOL_POINT),
               SymbolInfoDouble(g_sym, SYMBOL_TRADE_TICK_SIZE), SymbolInfoDouble(g_sym, SYMBOL_TRADE_CONTRACT_SIZE),
               (int)SymbolInfoInteger(g_sym, SYMBOL_TRADE_STOPS_LEVEL), (int)SymbolInfoInteger(g_sym, SYMBOL_TRADE_FREEZE_LEVEL),
               (int)SymbolInfoInteger(g_sym, SYMBOL_SPREAD), InpDryRun ? "true" : "false");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   IndicatorRelease(hE20); IndicatorRelease(hE50); IndicatorRelease(hE200);
   IndicatorRelease(hRsi); IndicatorRelease(hAtr);
}

void OnTick()
{
   ManagePosition();

   datetime bar = iTime(g_sym, InpTimeframe, 0);
   if(bar == 0 || (datetime)(long)GlobalVariableGet(g_gvBar) == bar) return;
   GlobalVariableSet(g_gvBar, (double)bar);   // mark first: one AI call per bar, even after a restart
   GlobalVariablesFlush();
   if(TimeCurrent() - bar > 60) { Print("SKIP LATE_BAR"); return; }   // attached or woke up mid-bar

   string why = PreCheck();
   if(why != "") { PrintFormat("SKIP %s", why); return; }

   double bid = SymbolInfoDouble(g_sym, SYMBOL_BID), ask = SymbolInfoDouble(g_sym, SYMBOL_ASK);
   double atr = 0;
   string body = BuildBody(bar, bid, ask, atr);
   if(body == "" || atr <= 0) { Print("SKIP NO_DATA"); return; }

   string resp;
   if(!Post(body, resp)) return;   // any bridge failure = no trade

   string p[];
   if(StringSplit(resp, ';', p) != 5 || (datetime)StringToInteger(p[4]) != bar)
   { PrintFormat("SKIP BAD_RESP '%s'", resp); return; }
   string act = p[0];
   if(act != "BUY" && act != "SELL") { PrintFormat("AI NONE bar=%s", TimeToString(bar)); return; }

   // the AI call may have taken up to 60 s: re-check the world
   if(iTime(g_sym, InpTimeframe, 0) != bar) { Print("SKIP BAR_CHANGED"); return; }
   double bid2 = SymbolInfoDouble(g_sym, SYMBOL_BID), ask2 = SymbolInfoDouble(g_sym, SYMBOL_ASK);
   if(MathAbs((bid2 + ask2) - (bid + ask)) / 2.0 > InpMaxDriftAtr * atr) { Print("SKIP DRIFT"); return; }

   double sl = 0, tp = 0, lots = 0;
   int conf = (int)StringToInteger(p[3]);
   why = Validate(act, StringToDouble(p[1]), StringToDouble(p[2]), conf, atr, bid2, ask2, sl, tp, lots);
   if(why != "") { PrintFormat("REJECT %s %s conf=%d", act, why, conf); return; }
   Execute(act, lots, sl, tp, conf);
}

string PreCheck()
{
   if(!InpDryRun && (!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED)))
      return "ALGO_OFF";
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double peak = MathMax(GlobalVariableGet(g_gvPeak), eq);
   GlobalVariableSet(g_gvPeak, peak);
   if(eq <= peak * (1.0 - InpMaxDrawdownPct / 100.0)) return "MAX_DD";   // reset the GV by hand (F3)
   if(HasPosition()) return "POSITION";
   MqlDateTime g;
   TimeToStruct(TimeGMT(), g);
   if(g.day_of_week == 0 || g.day_of_week == 6 || g.hour < InpStartHourGMT || g.hour >= InpEndHourGMT)
      return "HOURS";
   double spreadPts = (SymbolInfoDouble(g_sym, SYMBOL_ASK) - SymbolInfoDouble(g_sym, SYMBOL_BID)) / SymbolInfoDouble(g_sym, SYMBOL_POINT);
   if(spreadPts > InpMaxSpreadPts) return "SPREAD";
   if(TradesToday() >= InpMaxTradesPerDay) return "TRADES_DAY";
   if(DailyLossHit()) return "DAILY_LOSS";
   if(NewsBlackout()) return "NEWS";
   return "";
}

bool HasPosition()
{
   bool netting = AccountInfoInteger(ACCOUNT_MARGIN_MODE) != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetTicket(i) == 0 || PositionGetString(POSITION_SYMBOL) != g_sym) continue;
      if(netting || PositionGetInteger(POSITION_MAGIC) == InpMagic) return true;
   }
   return false;
}

int TradesToday()
{
   if(!HistorySelect(iTime(g_sym, PERIOD_D1, 0), TimeCurrent() + 60)) return 999;   // fail safe: block
   int n = 0;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong t = HistoryDealGetTicket(i);
      if(HistoryDealGetInteger(t, DEAL_MAGIC) == InpMagic &&
         HistoryDealGetString(t, DEAL_SYMBOL) == g_sym &&
         HistoryDealGetInteger(t, DEAL_ENTRY) == DEAL_ENTRY_IN) n++;
   }
   return n;
}

bool DailyLossHit()
{
   datetime day = iTime(g_sym, PERIOD_D1, 0);
   if((datetime)(long)GlobalVariableGet(g_gvDay) != day)
   {
      GlobalVariableSet(g_gvDay, (double)day);
      GlobalVariableSet(g_gvEq, AccountInfoDouble(ACCOUNT_EQUITY));
   }
   return AccountInfoDouble(ACCOUNT_EQUITY) <= GlobalVariableGet(g_gvEq) * (1.0 - InpMaxDailyLossPct / 100.0);
}

bool NewsBlackout()
{
   if(!InpNewsFilter) return false;
   MqlCalendarValue v[];
   datetime now = TimeTradeServer();   // calendar times are server time
   if(!CalendarValueHistory(v, now - InpNewsMinutes * 60, now + InpNewsMinutes * 60, NULL, "USD"))
   {
      PrintFormat("calendar error %d: blocking entries", GetLastError());
      return true;
   }
   for(int i = 0; i < ArraySize(v); i++)
   {
      MqlCalendarEvent e;
      if(CalendarEventById(v[i].event_id, e) && e.importance == CALENDAR_IMPORTANCE_HIGH) return true;
   }
   return false;
}

// Closed higher-timeframe bars, oldest first. "" on missing data.
string HtfCsv(const string title, ENUM_TIMEFRAMES tf, int d)
{
   int n = InpHtfBars;
   MqlRates r[];
   if(CopyRates(g_sym, tf, 1, n, r) != n) return "";
   string s = "# " + title + "\ntime,open,high,low,close\n";
   for(int i = 0; i < n; i++)
      s += TimeToString(r[i].time, TIME_DATE | TIME_MINUTES) + "," +
           DoubleToString(r[i].open, d) + "," + DoubleToString(r[i].high, d) + "," +
           DoubleToString(r[i].low, d) + "," + DoubleToString(r[i].close, d) + "\n";
   return s;
}

string BuildBody(datetime bar, double bid, double ask, double &atrLast)
{
   int n = InpBars;
   MqlRates r[];
   double e20[], e50[], e200[], rsi[], atr[];   // not series: index 0 = oldest
   if(CopyRates(g_sym, InpTimeframe, 1, n, r) != n) return "";   // shift 1 = closed bars only
   if(CopyBuffer(hE20, 0, 1, n, e20) != n || CopyBuffer(hE50, 0, 1, n, e50) != n ||
      CopyBuffer(hE200, 0, 1, n, e200) != n || CopyBuffer(hRsi, 0, 1, n, rsi) != n ||
      CopyBuffer(hAtr, 0, 1, n, atr) != n) return "";
   int d = (int)SymbolInfoInteger(g_sym, SYMBOL_DIGITS);
   string h1 = HtfCsv("H1", PERIOD_H1, d), h4 = HtfCsv("H4", PERIOD_H4, d);
   if(h1 == "" || h4 == "") return "";
   atrLast = atr[n - 1];
   string s = StringFormat("bar=%I64d;sym=%s;tf=%s;bid=%s;ask=%s;atr=%s\n", (long)bar, g_sym,
                           EnumToString(InpTimeframe), DoubleToString(bid, d), DoubleToString(ask, d),
                           DoubleToString(atrLast, d));
   s += "# tf\ntime,open,high,low,close,ema20,ema50,ema200,rsi14,atr14\n";
   for(int i = 0; i < n; i++)
      s += TimeToString(r[i].time, TIME_DATE | TIME_MINUTES) + "," +
           DoubleToString(r[i].open, d) + "," + DoubleToString(r[i].high, d) + "," +
           DoubleToString(r[i].low, d) + "," + DoubleToString(r[i].close, d) + "," +
           DoubleToString(e20[i], d) + "," + DoubleToString(e50[i], d) + "," +
           DoubleToString(e200[i], d) + "," + DoubleToString(rsi[i], 1) + "," +
           DoubleToString(atr[i], d) + "\n";
   return s + h1 + h4;
}

bool Post(const string body, string &resp)
{
   char data[], res[];
   string rh;
   int n = StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);
   if(n > 0) ArrayResize(data, n - 1);   // drop the trailing NUL
   ResetLastError();
   int code = WebRequest("POST", InpUrl, "Content-Type: text/plain\r\n", InpTimeoutMs, data, res, rh);
   if(code != 200) { PrintFormat("BRIDGE_ERR http=%d err=%d", code, GetLastError()); return false; }
   resp = CharArrayToString(res, 0, WHOLE_ARRAY, CP_UTF8);
   StringTrimLeft(resp);
   StringTrimRight(resp);
   return true;
}

double NormPrice(double price)
{
   double tick = SymbolInfoDouble(g_sym, SYMBOL_TRADE_TICK_SIZE);
   if(tick > 0) price = MathRound(price / tick) * tick;
   return NormalizeDouble(price, (int)SymbolInfoInteger(g_sym, SYMBOL_DIGITS));
}

double NormLots(double v)
{
   double step = SymbolInfoDouble(g_sym, SYMBOL_VOLUME_STEP);
   double mn = SymbolInfoDouble(g_sym, SYMBOL_VOLUME_MIN), mx = SymbolInfoDouble(g_sym, SYMBOL_VOLUME_MAX);
   if(step > 0) v = MathFloor(v / step + 1e-9) * step;
   return MathMax(mn, MathMin(mx, v));
}

string Validate(const string act, double slAtr, double rr, int conf, double atr,
                double bid, double ask, double &sl, double &tp, double &lots)
{
   if(!MathIsValidNumber(slAtr) || !MathIsValidNumber(rr)) return "BAD_NUM";
   if(conf < InpMinConfidence) return "CONF";
   if(slAtr < InpSlMinAtr || slAtr > InpSlMaxAtr) return "SL_ATR";
   if(rr < InpMinRR || rr > InpMaxRR) return "RR";
   if(slAtr * rr > InpMaxTpAtr) return "TP_ATR";

   bool   buy    = (act == "BUY");
   double entry  = buy ? ask : bid;            // real fill side
   double spread = ask - bid;
   double slDist = slAtr * atr, tpDist = slDist * rr;
   if(slDist < InpMinSlSpreads * spread) return "SL_SPREAD";

   double pt = SymbolInfoDouble(g_sym, SYMBOL_POINT);
   double minStop = (double)MathMax(SymbolInfoInteger(g_sym, SYMBOL_TRADE_STOPS_LEVEL),
                                    SymbolInfoInteger(g_sym, SYMBOL_TRADE_FREEZE_LEVEL)) * pt;
   if(slDist - spread < minStop || tpDist - spread < minStop) return "STOPS_LEVEL";

   sl   = NormPrice(buy ? entry - slDist : entry + slDist);
   tp   = NormPrice(buy ? entry + tpDist : entry - tpDist);
   lots = NormLots(InpLots);

   double pl = 0;
   if(!OrderCalcProfit(buy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, g_sym, lots, entry, sl, pl)) return "CALC";
   if(-pl > AccountInfoDouble(ACCOUNT_BALANCE) * InpMaxRiskPct / 100.0) return "RISK";
   return "";
}

void Execute(const string act, double lots, double sl, double tp, int conf)
{
   int d = (int)SymbolInfoInteger(g_sym, SYMBOL_DIGITS);
   if(InpDryRun)
   {
      PrintFormat("DRYRUN %s lots=%.2f sl=%s tp=%s conf=%d", act, lots,
                  DoubleToString(sl, d), DoubleToString(tp, d), conf);
      return;
   }
   bool ok = (act == "BUY") ? trade.Buy(lots, g_sym, 0.0, sl, tp, "AIGold")
                            : trade.Sell(lots, g_sym, 0.0, sl, tp, "AIGold");
   uint rc = trade.ResultRetcode();
   PrintFormat("ORDER %s ok=%s rc=%u (%s) req=%s fill=%s sl=%s tp=%s",
               act, ok ? "true" : "false", rc, trade.ResultRetcodeDescription(),
               DoubleToString(trade.RequestPrice(), d), DoubleToString(trade.ResultPrice(), d),
               DoubleToString(sl, d), DoubleToString(tp, d));
   if(!ok || (rc != TRADE_RETCODE_DONE && rc != TRADE_RETCODE_PLACED))
      Print("ORDER_FAIL: no retry, next chance is the next bar");
}

void ManagePosition()
{
   MqlDateTime g;
   TimeToStruct(TimeGMT(), g);
   bool fridayClose = (g.day_of_week == 5 && g.hour >= InpFridayCloseGMT);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetString(POSITION_SYMBOL) != g_sym || PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;
      int held = iBarShift(g_sym, InpTimeframe, (datetime)PositionGetInteger(POSITION_TIME));
      if(held >= InpMaxHoldBars || fridayClose)
      {
         if(!trade.PositionClose(t))
            PrintFormat("CLOSE_FAIL ticket=%I64u rc=%u", t, trade.ResultRetcode());
         else
            PrintFormat("TIME_EXIT ticket=%I64u held=%d bars friday=%s", t, held, fridayClose ? "true" : "false");
      }
   }
}
