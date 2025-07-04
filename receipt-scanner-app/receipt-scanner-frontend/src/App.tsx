import { useState, useRef, useEffect } from 'react';
import { Camera, Upload, ArrowLeft, FileDown, BarChart, AlertCircle, CheckCircle, Loader2, Trash2, Edit2 } from 'lucide-react';
import { Button } from './components/ui/button';
import { Card } from './components/ui/card';
import { Progress } from './components/ui/progress';
import { Alert, AlertDescription } from './components/ui/alert';
import { PieChart, Pie, Cell, ResponsiveContainer, Legend } from 'recharts';
import { uploadReceipt, getReceipts, exportReceipts, testUploadReceipt, healthCheck, getApiStatus, deleteReceipt, updateReceipt, getReceiptImageUrl } from './api';
import { ReceiptData } from './types';
import './App.css';

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#A569BD', '#5DADE2'];

function App() {
  const [view, setView] = useState<'home' | 'processing' | 'review' | 'list' | 'chart'>('home');
  const [receipts, setReceipts] = useState<ReceiptData[]>([]);
  const [currentReceipt, setCurrentReceipt] = useState<ReceiptData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isDeleting, setIsDeleting] = useState<number | null>(null);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);
  const [backendStatus, setBackendStatus] = useState<'unknown' | 'online' | 'offline'>('unknown');
  const [editingReceipt, setEditingReceipt] = useState<ReceiptData | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // バックエンドのヘルスチェック
  useEffect(() => {
    const checkBackendHealth = async () => {
      try {
        const isHealthy = await healthCheck();
        setBackendStatus(isHealthy ? 'online' : 'offline');
        
        if (isHealthy) {
          // APIステータスも確認
          const status = await getApiStatus();
          console.log('API Status:', status);
        }
      } catch (error) {
        console.error('Health check failed:', error);
        setBackendStatus('offline');
      }
    };

    checkBackendHealth();
    
    // 30秒ごとにヘルスチェック
    const interval = setInterval(checkBackendHealth, 30000);
    
    return () => clearInterval(interval);
  }, []);

  // レシート一覧の取得
  const fetchReceipts = async () => {
    if (backendStatus === 'online') {
      try {
        const response = await getReceipts();
        if (response.data && 'receipts' in response.data) {
          setReceipts(response.data.receipts || []);
        } else if (Array.isArray(response.data)) {
          setReceipts(response.data);
        }
      } catch (error) {
        console.error('Failed to fetch receipts:', error);
        setMessage({ text: 'レシート一覧の取得に失敗しました。', type: 'error' });
      }
    }
  };

  useEffect(() => {
    fetchReceipts();
  }, [backendStatus]);

  const handleFileUpload = async (file: File) => {
    if (backendStatus !== 'online') {
      setMessage({ text: 'バックエンドサーバーがオフラインです。しばらく待ってから再試行してください。', type: 'error' });
      return;
    }

    setView('processing');
    setIsLoading(true);
    setProgress(0);
    setMessage({ text: 'レシートを処理中...', type: 'info' });

    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 90) {
          clearInterval(interval);
          return 90;
        }
        return prev + 10;
      });
    }, 500);

    try {
      const response = await uploadReceipt(file);
      clearInterval(interval);
      setProgress(100);

      if (response.success && response.data) {
        setCurrentReceipt(response.data);
        setMessage({ text: response.message, type: 'success' });
        
        // 日付が自動補完された場合のメッセージを表示
        if (response.message.includes('日付は現在の日付で補完しました')) {
          setMessage({ 
            text: 'レシートから日付を読み取れなかったため、本日の日付を設定しました。必要に応じて修正してください。', 
            type: 'info' 
          });
        }
        
        setTimeout(() => {
          setView('review');
          setIsLoading(false);
        }, 500);
      } else {
        setMessage({ text: response.message || 'レシート処理に失敗しました。', type: 'error' });
        setTimeout(() => {
          setView('home');
          setIsLoading(false);
        }, 2000);
      }
    } catch (error) {
      clearInterval(interval);
      console.error('Upload error:', error);
      
      let errorMessage = 'エラーが発生しました。';
      if (error instanceof Error) {
        errorMessage = error.message;
      }
      
      setMessage({ text: errorMessage, type: 'error' });
      setTimeout(() => {
        setView('home');
        setIsLoading(false);
      }, 3000);
    }
  };

  const handleTestUpload = async () => {
    if (backendStatus !== 'online') {
      setMessage({ text: 'バックエンドサーバーがオフラインです。', type: 'error' });
      return;
    }

    setView('processing');
    setIsLoading(true);
    setProgress(0);
    setMessage({ text: 'テストレシートを処理中...', type: 'info' });

    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 90) {
          clearInterval(interval);
          return 90;
        }
        return prev + 10;
      });
    }, 300);

    try {
      const response = await testUploadReceipt();
      clearInterval(interval);
      setProgress(100);

      if (response.success && response.data) {
        setCurrentReceipt(response.data);
        setMessage({ text: response.message, type: 'success' });
        setTimeout(() => {
          setView('review');
          setIsLoading(false);
        }, 500);
      } else {
        setMessage({ text: response.message || 'テストレシート作成に失敗しました。', type: 'error' });
        setTimeout(() => {
          setView('home');
          setIsLoading(false);
        }, 2000);
      }
    } catch (error) {
      clearInterval(interval);
      console.error('Test upload error:', error);
      
      let errorMessage = 'テストレシート作成中にエラーが発生しました。';
      if (error instanceof Error) {
        errorMessage = error.message;
      }
      
      setMessage({ text: errorMessage, type: 'error' });
      setTimeout(() => {
        setView('home');
        setIsLoading(false);
      }, 2000);
    }
  };

  const handleSaveReceipt = async () => {
    if (currentReceipt) {
      // 編集モードの場合は更新
      if (editingReceipt && editingReceipt.id) {
        try {
          setIsLoading(true);
          const response = await updateReceipt(editingReceipt.id, currentReceipt);
          
          if (response.success) {
            await fetchReceipts();
            setMessage({ text: 'レシート情報を更新しました。', type: 'success' });
            setEditingReceipt(null);
            setTimeout(() => {
              setView('list');
              setMessage(null);
            }, 1000);
          } else {
            setMessage({ text: 'レシートの更新に失敗しました。', type: 'error' });
          }
        } catch (error) {
          console.error('Update error:', error);
          setMessage({ text: 'レシートの更新中にエラーが発生しました。', type: 'error' });
        } finally {
          setIsLoading(false);
        }
      } else {
        // 新規作成の場合
        await fetchReceipts();
        setMessage({ text: 'レシート情報を保存しました。', type: 'success' });
        setTimeout(() => {
          setView('list');
          setMessage(null);
        }, 1000);
      }
    }
  };

  const handleUpdateReceipt = (field: keyof ReceiptData, value: string | number | null) => {
    if (currentReceipt) {
      setCurrentReceipt({ ...currentReceipt, [field]: value });
    }
  };

  const handleDeleteReceipt = async (receiptId: number) => {
    if (confirm('このレシートを削除してもよろしいですか？')) {
      try {
        setIsDeleting(receiptId);
        const response = await deleteReceipt(receiptId);
        
        if (response.success) {
          await fetchReceipts();
          setMessage({ text: 'レシートを削除しました。', type: 'success' });
          setTimeout(() => setMessage(null), 3000);
        } else {
          setMessage({ text: 'レシートの削除に失敗しました。', type: 'error' });
        }
      } catch (error) {
        console.error('Delete error:', error);
        setMessage({ text: 'レシートの削除中にエラーが発生しました。', type: 'error' });
      } finally {
        setIsDeleting(null);
      }
    }
  };

  const handleEditReceipt = (receipt: ReceiptData) => {
    setCurrentReceipt(receipt);
    setEditingReceipt(receipt);
    setView('review');
  };

  const handleExportCSV = async () => {
    try {
      setIsLoading(true);
      setMessage({ text: 'CSVファイルを作成中...', type: 'info' });
      
      const csvData = await exportReceipts();
      
      const blob = new Blob([csvData], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `経費データ_${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '')}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      
      setIsLoading(false);
      setMessage({ text: 'CSVファイルをエクスポートしました。', type: 'success' });
      setTimeout(() => setMessage(null), 3000);
    } catch (error) {
      setIsLoading(false);
      console.error('Export error:', error);
      setMessage({ text: 'CSVエクスポート中にエラーが発生しました。', type: 'error' });
      setTimeout(() => setMessage(null), 3000);
    }
  };

  const getCategoryData = () => {
    const categories: Record<string, number> = {};
    
    receipts.forEach((receipt) => {
      const category = receipt.expense_category || '未分類';
      categories[category] = (categories[category] || 0) + receipt.total_amount;
    });
    
    return Object.entries(categories).map(([name, value]) => ({ name, value }));
  };

  // サーバー状態表示コンポーネント
  const ServerStatusIndicator = () => (
    <div className="fixed top-4 right-4 z-50">
      <div className={`flex items-center gap-2 px-3 py-2 rounded-full text-sm font-medium ${
        backendStatus === 'online' 
          ? 'bg-green-100 text-green-800' 
          : backendStatus === 'offline'
          ? 'bg-red-100 text-red-800'
          : 'bg-gray-100 text-gray-800'
      }`}>
        {backendStatus === 'online' && <CheckCircle className="h-4 w-4" />}
        {backendStatus === 'offline' && <AlertCircle className="h-4 w-4" />}
        {backendStatus === 'unknown' && <div className="h-4 w-4 rounded-full bg-gray-400 animate-pulse" />}
        {backendStatus === 'online' ? 'オンライン' : backendStatus === 'offline' ? 'オフライン' : '確認中'}
      </div>
    </div>
  );

  const HomeView = () => (
    <div className="flex flex-col items-center justify-center h-full gap-6">
      <h1 className="text-2xl font-bold text-gray-800">レシートスキャナー</h1>
      
      {backendStatus === 'offline' && (
        <Alert className="w-full max-w-sm bg-red-50 border-red-200">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription className="text-red-800">
            バックエンドサーバーに接続できません。しばらく待ってから再試行してください。
          </AlertDescription>
        </Alert>
      )}
      
      <div className="flex flex-col gap-4 w-full max-w-xs">
        <Button 
          className="h-16 text-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50"
          onClick={() => fileInputRef.current?.click()}
          disabled={backendStatus !== 'online' || isLoading}
        >
          {isLoading ? (
            <Loader2 className="mr-2 h-6 w-6 animate-spin" />
          ) : (
            <Camera className="mr-2 h-6 w-6" />
          )}
          レシートを撮影
        </Button>
        
        <Button 
          variant="outline" 
          className="h-12 text-base disabled:opacity-50"
          onClick={() => fileInputRef.current?.click()}
          disabled={backendStatus !== 'online' || isLoading}
        >
          {isLoading ? (
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          ) : (
            <Upload className="mr-2 h-5 w-5" />
          )}
          画像を選択
        </Button>
        
        {receipts.length > 0 && (
          <div className="flex gap-2 mt-4">
            <Button 
              variant="outline" 
              className="flex-1"
              onClick={() => setView('list')}
              disabled={isLoading}
            >
              レシート一覧
            </Button>
            <Button 
              variant="outline" 
              className="flex-1"
              onClick={() => setView('chart')}
              disabled={isLoading}
            >
              <BarChart className="mr-1 h-4 w-4" />
              グラフ
            </Button>
          </div>
        )}
        
        {/* 開発用テストボタン */}
        <Button 
          variant="ghost" 
          className="mt-4 text-sm text-gray-500 disabled:opacity-50"
          onClick={handleTestUpload}
          disabled={backendStatus !== 'online' || isLoading}
        >
          {isLoading ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : null}
          テストレシート追加
        </Button>
      </div>
      
      <input
        type="file"
        ref={fileInputRef}
        className="hidden"
        accept="image/jpeg,image/png,image/jpg"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) {
            handleFileUpload(file);
          }
        }}
      />
    </div>
  );

  const ProcessingView = () => (
    <div className="flex flex-col items-center justify-center h-full gap-6 p-4">
      <h2 className="text-xl font-semibold text-gray-800">処理中...</h2>
      <Progress value={progress} className="w-full max-w-xs" />
      <p className="text-gray-600">レシートから情報を抽出しています</p>
      {progress > 50 && (
        <p className="text-sm text-gray-500">
          {progress > 80 ? 'AI処理中...' : 'OCR処理中...'}
        </p>
      )}
    </div>
  );

  const ReviewView = () => {
    if (!currentReceipt) return null;
    
    return (
      <div className="flex flex-col h-full">
        <div className="flex items-center p-4 border-b">
          <Button 
            variant="ghost" 
            size="icon" 
            onClick={() => {
              setView('home');
              setEditingReceipt(null);
            }} 
            disabled={isLoading}
          >
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <h2 className="text-lg font-semibold ml-2">
            {editingReceipt ? 'レシート情報の編集' : 'レシート情報の確認'}
          </h2>
        </div>
        
        <div className="flex-1 overflow-auto p-4">
          <Card className="p-4">
            <div className="space-y-4">
              {/* レシート画像表示 */}
              {currentReceipt.id && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">レシート画像</label>
                  <div className="border rounded-md overflow-hidden">
                    <img
                      src={getReceiptImageUrl(currentReceipt.id)}
                      alt="Receipt"
                      className="w-full max-w-md mx-auto object-contain"
                      style={{ maxHeight: '400px' }}
                      onError={(e) => {
                        const target = e.target as HTMLImageElement;
                        target.style.display = 'none';
                        target.nextElementSibling?.classList.remove('hidden');
                      }}
                    />
                    <div className="hidden p-4 text-center text-gray-500">
                      画像を読み込めませんでした
                    </div>
                  </div>
                </div>
              )}
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  日付
                  {currentReceipt.date === new Date().toISOString().split('T')[0] && (
                    <span className="text-xs text-blue-600 ml-2">(自動補完)</span>
                  )}
                </label>
                <input
                  type="date"
                  className="w-full p-2 border rounded-md"
                  value={currentReceipt.date}
                  onChange={(e) => handleUpdateReceipt('date', e.target.value)}
                  disabled={isLoading}
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">店名</label>
                <input
                  type="text"
                  className="w-full p-2 border rounded-md"
                  value={currentReceipt.store_name}
                  onChange={(e) => handleUpdateReceipt('store_name', e.target.value)}
                  disabled={isLoading}
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">合計金額</label>
                <input
                  type="number"
                  className="w-full p-2 border rounded-md"
                  value={currentReceipt.total_amount}
                  onChange={(e) => handleUpdateReceipt('total_amount', parseFloat(e.target.value))}
                  disabled={isLoading}
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">税抜金額</label>
                <input
                  type="number"
                  className="w-full p-2 border rounded-md"
                  value={currentReceipt.tax_excluded_amount || ''}
                  onChange={(e) => handleUpdateReceipt('tax_excluded_amount', e.target.value ? parseFloat(e.target.value) : null)}
                  disabled={isLoading}
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">費目カテゴリー</label>
                <select
                  className="w-full p-2 border rounded-md"
                  value={currentReceipt.expense_category || ''}
                  onChange={(e) => handleUpdateReceipt('expense_category', e.target.value)}
                  disabled={isLoading}
                >
                  <option value="">選択してください</option>
                  <option value="交通費">交通費</option>
                  <option value="飲食費">飲食費</option>
                  <option value="消耗品費">消耗品費</option>
                  <option value="通信費">通信費</option>
                  <option value="接待交際費">接待交際費</option>
                  <option value="その他">その他</option>
                </select>
              </div>
              
              {currentReceipt.created_at && (
                <div className="text-xs text-gray-500">
                  アップロード日時: {new Date(currentReceipt.created_at).toLocaleString('ja-JP')}
                </div>
              )}
            </div>
          </Card>
        </div>
        
        <div className="p-4 border-t">
          <Button 
            className="w-full bg-blue-600 hover:bg-blue-700" 
            onClick={handleSaveReceipt}
            disabled={isLoading}
          >
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {editingReceipt ? '更新中...' : '保存中...'}
              </>
            ) : (
              editingReceipt ? '更新する' : '保存する'
            )}
          </Button>
        </div>
      </div>
    );
  };

  const ListView = () => (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center">
          <Button variant="ghost" size="icon" onClick={() => setView('home')} disabled={isLoading}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <h2 className="text-lg font-semibold ml-2">レシート一覧</h2>
        </div>
        
        <Button variant="outline" size="sm" onClick={handleExportCSV} disabled={isLoading}>
          {isLoading ? (
            <Loader2 className="h-4 w-4 mr-1 animate-spin" />
          ) : (
            <FileDown className="h-4 w-4 mr-1" />
          )}
          CSVエクスポート
        </Button>
      </div>
      
      <div className="flex-1 overflow-auto">
        {receipts.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full p-4 text-center">
            <p className="text-gray-500 mb-4">まだレシートが登録されていません。最初のレシートをスキャンしてみましょう！</p>
            <Button onClick={() => setView('home')} disabled={isLoading}>
              レシートを追加
            </Button>
          </div>
        ) : (
          <div className="divide-y">
            {receipts.map((receipt) => (
              <div key={receipt.id} className="p-4 hover:bg-gray-50 flex items-center">
                {/* サムネイル画像 */}
                {receipt.id && (
                  <div className="mr-3 flex-shrink-0">
                    <img
                      src={getReceiptImageUrl(receipt.id)}
                      alt="Receipt thumbnail"
                      className="w-12 h-12 rounded-md object-cover border"
                      onError={(e) => {
                        const target = e.target as HTMLImageElement;
                        target.style.display = 'none';
                        target.nextElementSibling?.classList.remove('hidden');
                      }}
                    />
                    <div className="hidden w-12 h-12 rounded-md border bg-gray-100 flex items-center justify-center">
                      <span className="text-xs text-gray-400">画像</span>
                    </div>
                  </div>
                )}
                
                <div className="flex-1">
                  <div className="flex justify-between items-start">
                    <div>
                      <p className="font-medium">{receipt.store_name}</p>
                      <p className="text-sm text-gray-500">{receipt.date}</p>
                    </div>
                    <div className="text-right">
                      <p className="font-semibold">¥{receipt.total_amount.toLocaleString()}</p>
                      <p className="text-xs text-gray-500">{receipt.expense_category || '未分類'}</p>
                    </div>
                  </div>
                </div>
                <div className="flex gap-2 ml-4">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleEditReceipt(receipt)}
                    disabled={isLoading || isDeleting === receipt.id}
                  >
                    <Edit2 className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => receipt.id && handleDeleteReceipt(receipt.id)}
                    disabled={isLoading || isDeleting === receipt.id}
                  >
                    {isDeleting === receipt.id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Trash2 className="h-4 w-4 text-red-500" />
                    )}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );

  const ChartView = () => (
    <div className="flex flex-col h-full">
      <div className="flex items-center p-4 border-b">
        <Button variant="ghost" size="icon" onClick={() => setView('home')} disabled={isLoading}>
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <h2 className="text-lg font-semibold ml-2">経費グラフ</h2>
      </div>
      
      <div className="flex-1 overflow-auto p-4">
        {receipts.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <p className="text-gray-500 mb-4">データがありません。レシートを追加するとグラフが表示されます。</p>
            <Button onClick={() => setView('home')} disabled={isLoading}>
              レシートを追加
            </Button>
          </div>
        ) : (
          <div className="h-80 mt-4">
            <h3 className="text-center text-gray-700 mb-4">費目別支出</h3>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={getCategoryData()}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="value"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                >
                  {getCategoryData().map((_, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );

  const MessageAlert = () => {
    if (!message) return null;
    
    return (
      <div className="fixed bottom-4 left-0 right-0 mx-auto w-full max-w-sm px-4 z-50">
        <Alert className={`
          ${message.type === 'success' ? 'bg-green-50 border-green-200' : ''}
          ${message.type === 'error' ? 'bg-red-50 border-red-200' : ''}
          ${message.type === 'info' ? 'bg-blue-50 border-blue-200' : ''}
        `}>
          <AlertDescription className={`
            ${message.type === 'success' ? 'text-green-800' : ''}
            ${message.type === 'error' ? 'text-red-800' : ''}
            ${message.type === 'info' ? 'text-blue-800' : ''}
          `}>
            {message.text}
          </AlertDescription>
        </Alert>
      </div>
    );
  };

  return (
    <div className="h-screen bg-gray-50 flex flex-col">
      <ServerStatusIndicator />
      
      {view === 'home' && <HomeView />}
      {view === 'processing' && <ProcessingView />}
      {view === 'review' && <ReviewView />}
      {view === 'list' && <ListView />}
      {view === 'chart' && <ChartView />}
      
      <MessageAlert />
    </div>
  );
}

export default App;
