// supabase/functions/receipt-upload/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

serve(async (req) => {
  // CORS preflight
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    // OpenAI API呼び出し
    const openaiResponse = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${Deno.env.get('OPENAI_API_KEY')}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: "gpt-4-vision-preview",
        messages: [
          {
            role: "user", 
            content: [
              {
                type: "text",
                text: "このレシートから店名、金額、日付を抽出してJSON形式で返してください"
              },
              {
                type: "image_url",
                image_url: {
                  url: "data:image/jpeg;base64,..." // アップロードされた画像
                }
              }
            ]
          }
        ],
        max_tokens: 500
      })
    })

    const aiResult = await openaiResponse.json()
    
    // Supabaseデータベースに保存
    const supabase = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_ANON_KEY') ?? ''
    )

    const { data, error } = await supabase
      .from('receipts')
      .insert([
        {
          store_name: aiResult.choices[0].message.content.store_name,
          total_amount: aiResult.choices[0].message.content.total_amount,
          date: aiResult.choices[0].message.content.date,
          created_at: new Date().toISOString()
        }
      ])

    if (error) throw error

    return new Response(
      JSON.stringify({ success: true, data: data }),
      { 
        headers: { 
          ...corsHeaders, 
          'Content-Type': 'application/json' 
        } 
      }
    )

  } catch (error) {
    return new Response(
      JSON.stringify({ error: error.message }),
      { 
        status: 400,
        headers: { 
          ...corsHeaders, 
          'Content-Type': 'application/json' 
        } 
      }
    )
  }
})