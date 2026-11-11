// ExportDeals.mq5 - writes MQL5/Files/deals_<symbol>.csv: one row per closed position of InpMagic,
// over the full account history (server-time unix). Read by tools/stats.py.
#property script_show_inputs
input string InpSymbol = "XAUUSD";
input long   InpMagic  = 20261029;

string Reason(long r)
{
   if(r == DEAL_REASON_SL) return "SL";
   if(r == DEAL_REASON_TP) return "TP";
   if(r == DEAL_REASON_EXPERT) return "EXPERT";
   if(r == DEAL_REASON_CLIENT || r == DEAL_REASON_MOBILE || r == DEAL_REASON_WEB) return "CLIENT";
   return "other";
}

void OnStart()
{
   if(!HistorySelect(0, TimeCurrent())) { PrintFormat("HistorySelect failed err=%d", GetLastError()); return; }
   int total = HistoryDealsTotal();
   // pass 1: entry deals of our magic (close deals by SL/TP or by hand may carry another magic)
   long pos[]; datetime t0[], t1[]; string side[]; double lots[], p0[], p1[], sl[], tp[], pl[], com[], swp[];
   string why[];
   for(int i = 0; i < total; i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(HistoryDealGetInteger(d, DEAL_ENTRY) != DEAL_ENTRY_IN || HistoryDealGetInteger(d, DEAL_MAGIC) != InpMagic ||
         HistoryDealGetString(d, DEAL_SYMBOL) != InpSymbol) continue;
      int n = ArraySize(pos) + 1;
      ArrayResize(pos, n); ArrayResize(t0, n); ArrayResize(t1, n); ArrayResize(side, n); ArrayResize(lots, n);
      ArrayResize(p0, n); ArrayResize(p1, n); ArrayResize(sl, n); ArrayResize(tp, n); ArrayResize(pl, n);
      ArrayResize(com, n); ArrayResize(swp, n); ArrayResize(why, n);
      n--;
      pos[n] = HistoryDealGetInteger(d, DEAL_POSITION_ID);
      t0[n] = (datetime)HistoryDealGetInteger(d, DEAL_TIME); t1[n] = 0;
      side[n] = HistoryDealGetInteger(d, DEAL_TYPE) == DEAL_TYPE_BUY ? "BUY" : "SELL";
      lots[n] = HistoryDealGetDouble(d, DEAL_VOLUME);
      p0[n] = HistoryDealGetDouble(d, DEAL_PRICE); p1[n] = 0;
      sl[n] = HistoryDealGetDouble(d, DEAL_SL); tp[n] = HistoryDealGetDouble(d, DEAL_TP);
      pl[n] = HistoryDealGetDouble(d, DEAL_PROFIT); com[n] = HistoryDealGetDouble(d, DEAL_COMMISSION);
      swp[n] = HistoryDealGetDouble(d, DEAL_SWAP); why[n] = "";
   }
   // pass 2: exit deals of those positions
   for(int i = 0; i < total; i++)
   {
      ulong d = HistoryDealGetTicket(i);
      long e = HistoryDealGetInteger(d, DEAL_ENTRY);
      if(e != DEAL_ENTRY_OUT && e != DEAL_ENTRY_OUT_BY) continue;
      long id = HistoryDealGetInteger(d, DEAL_POSITION_ID);
      for(int k = 0; k < ArraySize(pos); k++)
      {
         if(pos[k] != id) continue;
         t1[k] = (datetime)HistoryDealGetInteger(d, DEAL_TIME);
         p1[k] = HistoryDealGetDouble(d, DEAL_PRICE);
         pl[k] += HistoryDealGetDouble(d, DEAL_PROFIT);
         com[k] += HistoryDealGetDouble(d, DEAL_COMMISSION);
         swp[k] += HistoryDealGetDouble(d, DEAL_SWAP);
         why[k] = Reason(HistoryDealGetInteger(d, DEAL_REASON));
         break;
      }
   }
   int dg = (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS);
   int f = FileOpen("deals_" + InpSymbol + ".csv", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(f == INVALID_HANDLE) { PrintFormat("FileOpen failed err=%d", GetLastError()); return; }
   FileWriteString(f, "position,open_time,close_time,type,lots,open_price,close_price,sl,tp,profit,commission,swap,close_reason\n");
   int rows = 0;
   for(int k = 0; k < ArraySize(pos); k++)
   {
      if(t1[k] == 0) continue;   // still open
      FileWriteString(f, StringFormat("%I64d,%I64d,%I64d,%s,%.2f,%s,%s,%s,%s,%.2f,%.2f,%.2f,%s\n", pos[k],
                      (long)t0[k], (long)t1[k], side[k], lots[k], DoubleToString(p0[k], dg), DoubleToString(p1[k], dg),
                      DoubleToString(sl[k], dg), DoubleToString(tp[k], dg), pl[k], com[k], swp[k], why[k]));
      rows++;
   }
   FileClose(f);
   PrintFormat("wrote %d closed positions", rows);
}
