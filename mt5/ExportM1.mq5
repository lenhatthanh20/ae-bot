// ExportM1.mq5 - writes MQL5/Files/m1_<symbol>.csv (server-time unix, bid prices)
#property script_show_inputs
input string InpSymbol = "XAUUSD";
input int    InpDays   = 60;

void OnStart()
{
   MqlRates r[];
   int n = CopyRates(InpSymbol, PERIOD_M1, TimeCurrent() - InpDays * 86400, TimeCurrent(), r);
   if(n <= 0) { PrintFormat("CopyRates failed err=%d", GetLastError()); return; }
   int d = (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS);
   int f = FileOpen("m1_" + InpSymbol + ".csv", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(f == INVALID_HANDLE) { PrintFormat("FileOpen failed err=%d", GetLastError()); return; }
   FileWriteString(f, "time,open,high,low,close\n");
   for(int i = 0; i < n; i++)
      FileWriteString(f, StringFormat("%I64d,%s,%s,%s,%s\n", (long)r[i].time,
                      DoubleToString(r[i].open, d), DoubleToString(r[i].high, d),
                      DoubleToString(r[i].low, d), DoubleToString(r[i].close, d)));
   FileClose(f);
   PrintFormat("wrote %d M1 bars", n);
}
